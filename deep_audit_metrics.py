import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

for date in ['2026-10-20', '2026-10-21']:
    print(f"\n==========================================")
    print(f"       DEEP AUDIT METRICS: {date}")
    print(f"==========================================")
    with open(f'ad_level_insights_{date}.json', 'r', encoding='utf-8') as f:
        res = json.load(f)
        
    ads = res.get('data', [])
    print(f"Total active ads tracked: {len(ads)}")
    
    # Group by Campaign -> Adset -> Ad
    campaigns = {}
    for a in ads:
        cname = a.get('campaign_name')
        adset = a.get('adset_name')
        adname = a.get('ad_name')
        spend = float(a.get('spend', 0))
        impr = int(a.get('impressions', 0))
        reach = int(a.get('reach', 0))
        clicks = int(a.get('clicks', 0))
        cpc = float(a.get('cpc', 0)) if a.get('cpc') else 0
        ctr = float(a.get('ctr', 0)) if a.get('ctr') else 0
        
        actions = {act['action_type']: act['value'] for act in a.get('actions', [])}
        msg = actions.get('onsite_conversion.messaging_conversation_started_7d', 
              actions.get('messaging_conversation_started_7d', 0))
        
        if cname not in campaigns:
            campaigns[cname] = {'spend': 0, 'impr': 0, 'reach': 0, 'clicks': 0, 'msg': 0, 'ads': []}
            
        campaigns[cname]['spend'] += spend
        campaigns[cname]['impr'] += impr
        campaigns[cname]['reach'] += reach
        campaigns[cname]['clicks'] += clicks
        campaigns[cname]['msg'] += int(msg)
        campaigns[cname]['ads'].append({
            'adset': adset,
            'adname': adname,
            'spend': spend,
            'clicks': clicks,
            'cpc': cpc,
            'ctr': ctr,
            'msg': int(msg),
            'cost_msg': (spend / int(msg)) if int(msg) > 0 else 0
        })
        
    for cname, cdata in campaigns.items():
        cost_msg = (cdata['spend'] / cdata['msg']) if cdata['msg'] > 0 else 0
        avg_cpc = (cdata['spend'] / cdata['clicks']) if cdata['clicks'] > 0 else 0
        avg_ctr = (cdata['clicks'] / cdata['impr'] * 100) if cdata['impr'] > 0 else 0
        print(f"\n📢 CAMPAIGN: {cname}")
        print(f"   Spend: ฿{cdata['spend']:,.2f} | Reach: {cdata['reach']:,} | Impr: {cdata['impr']:,}")
        print(f"   Clicks: {cdata['clicks']} | Avg CPC: ฿{avg_cpc:.2f} | Avg CTR: {avg_ctr:.2f}%")
        print(f"   Messages: {cdata['msg']} | Cost/Msg: ฿{cost_msg:.2f}")
        for ad in cdata['ads']:
            print(f"     └─ Ad: {ad['adname'][:35]} | Spend: ฿{ad['spend']:,.2f} | Clicks: {ad['clicks']} | CTR: {ad['ctr']:.2f}% | Msg: {ad['msg']} (฿{ad['cost_msg']:.2f})")
