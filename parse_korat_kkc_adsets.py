import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('korat_kkc_audit.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

adsets = {a['id']: a for a in data['adsets']}
insights = data['insights']
ads = data['ads']

target_campaign_ids = [
    '120251706393360040', # โคราช เปิดร้านโพส 1 23-31 ตุลา
    '120251706685980040', # โคราช เปิดร้านโพส 1 23-31 retarget ทัก
    '120251592451670040', # ขอนแก่น รีวิวลค  แอม
    '120251613068960040', # ขอนแก่น รีวิวลค  แอม 12-18 ตุลา
]

# Map ads to adsets
ads_by_adset = {}
for a in ads:
    asid = a.get('adset_id')
    if asid not in ads_by_adset:
        ads_by_adset[asid] = []
    ads_by_adset[asid].append(a)

# Group insights by adset and date
ins_by_adset = {}
for row in insights:
    asid = row.get('adset_id')
    d = row.get('date_start')
    if asid not in ins_by_adset:
        ins_by_adset[asid] = {}
    ins_by_adset[asid][d] = row

print("==================================================================")
print("             AUDIT KORAT & KKC AD SETS & CREATIVES                ")
print("==================================================================")

for cid in target_campaign_ids:
    c_adsets = [a for a in adsets.values() if a.get('campaign_id') == cid]
    cname = c_adsets[0]['name'] if c_adsets else cid
    # Get campaign name from insights
    for row in insights:
        if row.get('campaign_id') == cid:
            cname = row.get('campaign_name')
            break
            
    print(f"\n==================================================================")
    print(f"🔥 CAMPAIGN: {cname} (ID: {cid})")
    print(f"==================================================================")
    
    for aset in c_adsets:
        asid = aset['id']
        as_name = aset['name']
        status = aset['status']
        eff_status = aset['effective_status']
        budget = aset.get('daily_budget')
        goal = aset.get('optimization_goal')
        targeting = aset.get('targeting', {})
        
        # Targeting summary
        geo = targeting.get('geo_locations', {})
        cities = geo.get('cities', [])
        regions = geo.get('regions', [])
        custom_locs = geo.get('custom_locations', [])
        age_min = targeting.get('age_min')
        age_max = targeting.get('age_max')
        genders = targeting.get('genders')
        custom_audiences = targeting.get('custom_audiences', [])
        
        target_desc = f"Age: {age_min}-{age_max}, Genders: {genders}"
        if cities:
            target_desc += f", Cities: {[c.get('name') for c in cities]}"
        if regions:
            target_desc += f", Regions: {[r.get('name') for r in regions]}"
        if custom_locs:
            target_desc += f", Radius: {len(custom_locs)} custom pin(s)"
        if custom_audiences:
            target_desc += f", Custom Audiences: {[ca.get('name') for ca in custom_audiences]}"
            
        print(f"\n👉 [ชุดโฆษณา / Ad Set] {as_name}")
        print(f"   ID: {asid} | Status: {status} ({eff_status}) | Goal: {goal} | Budget: {budget}")
        print(f"   Targeting: {target_desc}")
        
        # Show 20 & 21 Oct insights
        as_ins = ins_by_adset.get(asid, {})
        for d in ['2026-10-20', '2026-10-21']:
            if d in as_ins:
                r = as_ins[d]
                spend = float(r.get('spend', 0))
                reach = int(r.get('reach', 0))
                impr = int(r.get('impressions', 0))
                clicks = int(r.get('clicks', 0))
                cpc = float(r.get('cpc', 0)) if r.get('cpc') else 0
                ctr = float(r.get('ctr', 0)) if r.get('ctr') else 0
                cpm = float(r.get('cpm', 0)) if r.get('cpm') else 0
                actions = {act['action_type']: act['value'] for act in r.get('actions', [])}
                msg = actions.get('onsite_conversion.messaging_conversation_started_7d', 
                      actions.get('messaging_conversation_started_7d', 0))
                cost_msg = (spend / float(msg)) if msg and float(msg) > 0 else 0
                post_eng = actions.get('post_engagement', 0)
                video_views = actions.get('video_view', 0)
                print(f"   📅 {d}: Spend ฿{spend:,.2f} | Clicks {clicks} | CTR {ctr:.2f}% | CPC ฿{cpc:.2f} | CPM ฿{cpm:.2f} | Msg: {msg} (฿{cost_msg:.2f}) | Eng: {post_eng} | Views: {video_views}")
            else:
                print(f"   📅 {d}: ไม่มีข้อมูล / ไม่ได้รัน")
                
        # Show Ads under this Ad Set
        as_ads = ads_by_adset.get(asid, [])
        for ad in as_ads:
            ad_name = ad.get('name')
            ad_status = ad.get('status')
            creative = ad.get('creative', {})
            c_name = creative.get('name')
            c_body = creative.get('body')
            c_story = creative.get('effective_object_story_id')
            body_prev = (c_body[:50] + '...') if c_body else 'None'
            print(f"     └─ [Ad] {ad_name} | Status: {ad_status} | Creative: {c_name} | Story: {c_story} | Text: {body_prev}")
