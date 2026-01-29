"""Test conflict resolution in calculation."""
from multi_memo_engine import create_multi_memo_engine
from datetime import datetime

engine = create_multi_memo_engine('../artifact')
engine.retrieve_and_prepare(target_date=datetime(2026, 1, 28))

context = {
    'base_price': 1500000,
    'block': 'A',
    'floor_level': 25,
    'buyer_type': 'local',
    'unit_type': 'A1',
    'buyer_is_bumi': False
}

result = engine.calculate(context, spa_date='28 Jan 2026')

print('=== COMMISSION BREAKDOWN ===')
for c in result.commission_breakdown:
    print(f'{c.rule_name} ({c.rule_id})')
    print(f'  Memo: {c.memo_reference}')
    print(f'  Amount: RM {c.calculated_amount:,.2f}')
    print()

print(f'Total Commission: RM {result.total_commission:,.2f}')
print(f'Commission rules applied: {len(result.commission_breakdown)}')

print()
print('=== RUNTIME CONFLICTS ===')
for c in result.conflicts_detected:
    if isinstance(c, dict) and c.get('conflict_type') == 'runtime_resolution':
        print(f"Winner: {c['winner']['rule_name']} ({c['winner']['memo_reference']})")
        for l in c.get('losers', []):
            print(f"  Superseded: {l['rule_name']} ({l['memo_reference']})")
