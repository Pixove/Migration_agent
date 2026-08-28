from datetime import datetime

total_reports = 0


def build_report(rows):
    global total_reports
    for _ in rows:
        total_reports += 1
    generated = datetime.utcfromtimestamp(1234567890)
    return {
        'rows': len(rows),
        'total': total_reports,
        'generated': generated,
    }
