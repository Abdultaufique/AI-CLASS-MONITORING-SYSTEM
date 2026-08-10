"""
Report Generator — produces session engagement reports from AttentionSnapshot data.

Generates:
  • Attention-over-time time series (timestamp + class_pct points).
  • Low-attention dip timestamps (runs of snapshots below threshold).
  • Summary statistics (avg %, min %, max %, total dip duration).
  • CSV export (consistent with monitoring/views.py export_csv pattern).

IMPORTANT DISCLAIMER — report accuracy notice:
  All metrics in this report are derived from the geometric heuristic attention
  classifier (head pose + eye closure). They represent an APPROXIMATION of
  visual engagement indicators only. They are not a validated measure of learning
  or cognitive attention. Reports should be used as rough teacher feedback only,
  never as the sole basis for disciplinary or academic decisions.
"""
import csv
import logging
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def generate_session_report(session_id: str) -> Optional[Dict]:
    """
    Generate a complete engagement report for a finished (or active) session.

    Args:
        session_id: UUID string of an AttentionSession.

    Returns:
        Dict with keys:
            session:       Session metadata dict
            time_series:   List of {timestamp_iso, elapsed_secs, class_pct}
            dip_periods:   List of {start_iso, end_iso, duration_secs, min_pct}
            summary:       Summary stats dict
        Returns None if session not found.
    """
    from apps.attention.models import AttentionSession, AttentionSnapshot

    try:
        session = AttentionSession.objects.select_related(
            'organization', 'camera'
        ).get(id=session_id)
    except AttentionSession.DoesNotExist:
        logger.error("Session not found: %s", session_id)
        return None

    snapshots = list(session.snapshots.order_by('timestamp'))
    if not snapshots:
        return {
            'session':     _session_meta(session),
            'time_series': [],
            'dip_periods': [],
            'summary':     {
                'avg_pct': None, 'min_pct': None, 'max_pct': None,
                'total_dip_duration_secs': 0, 'dip_count': 0,
                'total_snapshots': 0,
            },
        }

    # ── Time series ──────────────────────────────────────────────────────────
    session_start = session.started_at
    time_series   = []
    for snap in snapshots:
        elapsed = (snap.timestamp - session_start).total_seconds()
        time_series.append({
            'timestamp_iso': snap.timestamp.isoformat(),
            'elapsed_secs':  round(elapsed, 1),
            'class_pct':     round(snap.class_attention_pct, 4),
            'total_faces':   snap.total_faces,
            'attentive':     snap.attentive_count,
            'distracted':    snap.distracted_count,
            'alert_active':  snap.alert_active,
        })

    # ── Dip periods (consecutive below-threshold snapshots) ──────────────────
    threshold  = session.alert_threshold
    dip_periods = _find_dip_periods(snapshots, threshold, session_start)

    # ── Summary stats ─────────────────────────────────────────────────────────
    pcts = [s.class_attention_pct for s in snapshots]
    total_dip = sum(d['duration_secs'] for d in dip_periods)

    summary = {
        'avg_pct':                   round(sum(pcts) / len(pcts), 4) if pcts else None,
        'min_pct':                   round(min(pcts), 4) if pcts else None,
        'max_pct':                   round(max(pcts), 4) if pcts else None,
        'total_dip_duration_secs':   round(total_dip, 1),
        'dip_count':                 len(dip_periods),
        'total_snapshots':           len(snapshots),
        'alert_threshold':           threshold,
        'disclaimer': (
            'These figures are geometric-heuristic approximations, not validated '
            'attention measurements. Use as rough teacher feedback only.'
        ),
    }

    return {
        'session':     _session_meta(session),
        'time_series': time_series,
        'dip_periods': dip_periods,
        'summary':     summary,
    }


def _session_meta(session) -> Dict:
    return {
        'id':             str(session.id),
        'organization':   session.organization.name,
        'camera':         session.camera.name if session.camera else 'N/A',
        'started_at':     session.started_at.isoformat(),
        'ended_at':       session.ended_at.isoformat() if session.ended_at else None,
        'status':         session.status,
        'aggregate_only': session.aggregate_only,
        'duration_secs':  session.duration_secs,
    }


def _find_dip_periods(
    snapshots: list,
    threshold: float,
    session_start,
) -> List[Dict]:
    """
    Identify contiguous runs of snapshots below the alert threshold.
    Returns list of dip period dicts.
    """
    dips = []
    in_dip        = False
    dip_start     = None
    dip_min_pct   = 1.0

    for snap in snapshots:
        if snap.class_attention_pct < threshold:
            if not in_dip:
                in_dip    = True
                dip_start = snap.timestamp
                dip_min_pct = snap.class_attention_pct
            else:
                dip_min_pct = min(dip_min_pct, snap.class_attention_pct)
        else:
            if in_dip:
                duration = (snap.timestamp - dip_start).total_seconds()
                dips.append({
                    'start_iso':    dip_start.isoformat(),
                    'end_iso':      snap.timestamp.isoformat(),
                    'elapsed_start': round((dip_start - session_start).total_seconds(), 1),
                    'duration_secs': round(duration, 1),
                    'min_pct':      round(dip_min_pct, 4),
                })
                in_dip = False

    # Close open dip at end of session
    if in_dip and snapshots:
        last = snapshots[-1]
        duration = (last.timestamp - dip_start).total_seconds()
        dips.append({
            'start_iso':    dip_start.isoformat(),
            'end_iso':      last.timestamp.isoformat(),
            'elapsed_start': round((dip_start - session_start).total_seconds(), 1),
            'duration_secs': round(duration, 1),
            'min_pct':      round(dip_min_pct, 4),
        })

    return dips


def generate_csv(report: Dict) -> str:
    """
    Serialize a report dict to CSV text (consistent with monitoring/views.py pattern).
    Returns CSV string.
    """
    output = StringIO()
    writer = csv.writer(output)

    # ── Header block ─────────────────────────────────────────────────────────
    sess  = report['session']
    summ  = report['summary']
    writer.writerow(['=== LSOYS AI — Classroom Attention Monitoring Report ==='])
    writer.writerow([
        'NOTICE: These values are geometric approximations, not validated '
        'attention measurements. For teacher feedback only.'
    ])
    writer.writerow([])
    writer.writerow(['Session ID',       sess['id']])
    writer.writerow(['Organization',     sess['organization']])
    writer.writerow(['Camera',           sess['camera']])
    writer.writerow(['Started At',       sess['started_at']])
    writer.writerow(['Ended At',         sess.get('ended_at') or 'In progress'])
    writer.writerow(['Status',           sess['status']])
    writer.writerow(['Aggregate Only',   'Yes' if sess['aggregate_only'] else 'No'])
    writer.writerow([])

    # ── Summary ───────────────────────────────────────────────────────────────
    writer.writerow(['=== Summary Statistics ==='])
    writer.writerow(['Average Attention',
                     f"{summ['avg_pct']:.1%}" if summ['avg_pct'] is not None else 'N/A'])
    writer.writerow(['Minimum Attention',
                     f"{summ['min_pct']:.1%}" if summ['min_pct'] is not None else 'N/A'])
    writer.writerow(['Maximum Attention',
                     f"{summ['max_pct']:.1%}" if summ['max_pct'] is not None else 'N/A'])
    writer.writerow(['Low-Attention Dip Count',    summ['dip_count']])
    writer.writerow(['Total Dip Duration (s)',      summ['total_dip_duration_secs']])
    writer.writerow(['Total Snapshots',             summ['total_snapshots']])
    writer.writerow([])

    # ── Dip periods ───────────────────────────────────────────────────────────
    if report['dip_periods']:
        writer.writerow(['=== Low-Attention Dip Periods ==='])
        writer.writerow([
            'Dip #', 'Start (ISO)', 'Elapsed Start (s)',
            'Duration (s)', 'Min Attention %'
        ])
        for i, dip in enumerate(report['dip_periods'], 1):
            writer.writerow([
                i,
                dip['start_iso'],
                dip['elapsed_start'],
                dip['duration_secs'],
                f"{dip['min_pct']:.1%}",
            ])
        writer.writerow([])

    # ── Time series ───────────────────────────────────────────────────────────
    writer.writerow(['=== Attention Over Time ==='])
    writer.writerow([
        'Timestamp (ISO)', 'Elapsed (s)', 'Class Attention %',
        'Total Faces', 'Attentive', 'Distracted', 'Alert Active'
    ])
    for pt in report['time_series']:
        writer.writerow([
            pt['timestamp_iso'],
            pt['elapsed_secs'],
            f"{pt['class_pct']:.1%}",
            pt['total_faces'],
            pt['attentive'],
            pt['distracted'],
            'Yes' if pt['alert_active'] else 'No',
        ])

    return output.getvalue()
