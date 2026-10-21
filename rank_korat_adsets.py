import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('korat_kkc_audit.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

adsets = {a['id']: a for a in data['adsets']}
insights = data['insights']

cid = '120251706685980040' # โคราช retarget ทัก
c_adsets = [a for a in adsets.values() if a.get('campaign_id') == cid]

print(f"Total Ad Sets in Korat Retarget: {len(c_adsets)}")

stats = {}
for r in insights:
    if r.get('campaign_id') == cid:
        asid = r.get('adset_id')
        asname = r.get('adset_name')
        if asname not in stats:
            stats[asname] = {'spend': 0, 'clicks': 0, 'impr': 0, 'msg': 0}
        stats[asname]['spend'] += float(r.get('spend', 0))
        stats[asname]['clicks'] += int(r.get('clicks', 0))
        stats[asname]['impr'] += int(r.get('impressions', 0))
        actions = {act['action_type']: act['value'] for act in r.get('actions', [])}
        msg = actions.get('onsite_conversion.messaging_conversation_started_7d', 
              actions.get('messaging_conversation_started_7d', 0))
        stats[asname]['msg'] += int(msg)

print(f"{'ชุดโฆษณา (Ad Set)':<20} | {'Spend (2 วัน)':<12} | {'Clicks':<8} | {'CTR %':<8} | {'CPC':<8} | {'Msg':<5} | {'Cost/Msg'}")
print("-" * 80)
for asname, s in sorted(stats.items(), key=lambda x: x[1]['msg'], reverse=True):
    ctr = (s['clicks'] / s['impr'] * 100) if s['impr'] > 0 else 0
    cpc = (s['spend'] / s['clicks']) if s['clicks'] > 0 else 0
    cost_msg = (s['spend'] / s['msg']) if s['msg'] > 0 else 0
    print(f"{asname:<20} | ฿{s['spend']:<11.2f} | {s['clicks']:<8} | {ctr:<7.2f}% | ฿{cpc:<6.2f} | {s['msg']:<5} | ฿{cost_msg:.2f}")
