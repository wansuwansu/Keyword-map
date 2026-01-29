import streamlit as st
import streamlit.components.v1 as components
import time
import requests
import pandas as pd
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
import random
import re

# [지도 라이브러리]
import folium
from streamlit_folium import st_folium

# ==========================================
# 0. API 키 및 설정
# ==========================================

# [1] 카카오 API (필수)
KAKAO_REST_KEY = "968344aed4aff4d7aeb37eb199767d5a"

# [2] 네이버 광고 API
AD_API_KEY = "01000000002855c92d066a6e30d3eaeafbe6adebd688d73c3dd901f151b52c430ddcad5c88"
AD_SECRET_KEY = "AQAAAAAoVcktBmpuMNPq6vvmrevWXrbXSbEoh/+/3U3vTcTLyA=="
AD_CUSTOMER_ID = "4173931"

# [3] 기타 설정
NAVER_SEARCH_ID = "dlOt9fIfGfpSj69uICWc"
NAVER_SEARCH_SECRET = "_rtIqpqYpd"
YOUTUBE_API_KEY = "AIzaSyBPgiYOvrPJ4cacWQ42UQb_KZobCcpOIH0"

EXCLUDED_KEYWORDS = ["슈링크", "써마지", "울쎄라", "인모드", "티타늄"] 

# ==========================================
# 1. 핵심 기능 함수
# ==========================================

def search_places_kakao(query):
    """장소 검색"""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        res = requests.get(url, params={"query": query, "size": 15}, headers=headers)
        return res.json()['documents'] if res.status_code == 200 else []
    except: return []

def get_address_details_kakao(address_str):
    """주소 -> 좌표 + 법정동 분석"""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        res = requests.get(url, params={"query": address_str}, headers=headers)
        if res.status_code == 200:
            docs = res.json()['documents']
            if docs:
                data = docs[0]
                x, y = float(data['x']), float(data['y'])
                addr = data.get('address', {})
                
                region_1 = addr.get('region_1depth_name', '') # 충북
                region_2 = addr.get('region_2depth_name', '') # 청주시 상당구
                
                city_name = ""
                gu_name = ""
                if region_2:
                    parts = region_2.split()
                    if len(parts) >= 2:
                        city_name = parts[0] # 청주시
                        gu_name = parts[1]   # 상당구
                    else:
                        gu_name = parts[0]   # 강남구
                
                b_dong = addr.get('region_3depth_name', '') # 법정동
                return x, y, region_1, city_name, gu_name, b_dong
        return 0.0, 0.0, "", "", "", ""
    except: return 0.0, 0.0, "", "", "", ""

def get_admin_dong(x, y):
    """행정동 추출 (중앙동 등)"""
    if x == 0.0 or y == 0.0: return ""
    url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        res = requests.get(url, params={"x": x, "y": y}, headers=headers)
        if res.status_code == 200:
            docs = res.json()['documents']
            for doc in docs:
                if doc['region_type'] == 'H': return doc['region_3depth_name']
        return ""
    except: return ""

def get_nearby_stations(x, y):
    if x == 0.0 or y == 0.0: return []
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    params = {"category_group_code": "SW8", "x": x, "y": y, "radius": 1500, "sort": "distance"}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200:
            return [{"name": d['place_name'], "clean_name": d['place_name'].split()[0].replace("역",""), "x": float(d['x']), "y": float(d['y'])} for d in res.json()['documents']][:4]
        return []
    except: return []

def get_naver_expanded_rankings(seed_keywords, category_seed, filters, loc_info):
    """
    [핵심] 위치 기반 필터링 (화이트리스트 방식)
    """
    uri = '/keywordstool'
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}.GET.{uri}"
    signature = base64.b64encode(hmac.new(bytes(AD_SECRET_KEY, 'UTF-8'), bytes(msg, 'UTF-8'), hashlib.sha256).digest())
    headers = {'X-Timestamp': timestamp, 'X-API-KEY': AD_API_KEY, 'X-Customer': AD_CUSTOMER_ID, 'X-Signature': signature}
    
    clean_seeds = []
    seen = set()
    for k in seed_keywords:
        k_nospace = k.replace(" ", "")
        if k_nospace not in seen:
            clean_seeds.append(k_nospace)
            seen.add(k_nospace)
            
    # [화이트리스트] 행정구역 및 역 이름 정의
    valid_local_terms = []
    if loc_info['si']: valid_local_terms.append(loc_info['si'].replace("시", "")) 
    if loc_info['gu']: valid_local_terms.append(loc_info['gu']) 
    if loc_info['b_dong']: valid_local_terms.append(re.sub(r'\d+가?', '', loc_info['b_dong'])) 
    if loc_info['h_dong']: valid_local_terms.append(loc_info['h_dong']) 
    for s in loc_info['stations']: valid_local_terms.append(s['clean_name'])
    valid_local_terms = list(set(valid_local_terms))

    all_results = []
    seen_kwd = set()
    
    for i in range(0, len(clean_seeds), 5):
        chunk = clean_seeds[i:i+5]
        try:
            res = requests.get("https://api.naver.com" + uri, params={'hintKeywords': ','.join(chunk), 'showDetail': '1'}, headers=headers)
            if res.status_code == 200:
                data = res.json()
                for item in data.get('keywordList', []):
                    kwd = item['relKeyword'].replace(" ", "")
                    if kwd in seen_kwd: continue
                    if category_seed not in kwd: continue 
                    if kwd == category_seed: continue 
                    if any(bad in kwd for bad in EXCLUDED_KEYWORDS): continue
                    
                    is_local_relevant = False
                    for term in valid_local_terms:
                        if term in kwd:
                            is_local_relevant = True
                            break
                    if not is_local_relevant: continue 

                    if not filters['station']:
                        if "역" in kwd: continue
                        is_station_word = False
                        for s in loc_info['stations']:
                            if s['clean_name'] in kwd: is_station_word = True; break
                        if is_station_word: continue

                    priority = 0
                    if kwd in clean_seeds: priority = 100
                    for main_k in loc_info['main_keywords']:
                        if main_k in kwd: priority += 20
                    
                    seen_kwd.add(kwd)
                    pc = item['monthlyPcQcCnt']
                    mo = item['monthlyMobileQcCnt']
                    if isinstance(pc, str): pc = 10
                    if isinstance(mo, str): mo = 10
                    all_results.append({'key': item['relKeyword'], 'total': pc + mo, 'priority': priority})
            time.sleep(0.1)
        except: pass
    return sorted(all_results, key=lambda x: (x['priority'], x['total']), reverse=True)

def search_bloggers(keyword, display=30):
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": NAVER_SEARCH_ID, "X-Naver-Client-Secret": NAVER_SEARCH_SECRET}
    params = {"query": keyword, "display": display, "sort": "sim"}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200: return res.json()['items']
        return None
    except: return None

# ==========================================
# 2. 메인 UI
# ==========================================
st.set_page_config(page_title="병원 마케팅 마스터", layout="wide")

st.markdown("""
    <style>
        #myBtn { display: flex; justify-content: center; align-items: center; position: fixed; bottom: 30px; right: 30px; z-index: 9999;
            font-size: 20px; border: none; outline: none; background-color: #E1306C; color: white; cursor: pointer; width: 50px; height: 50px;
            padding: 0; border-radius: 50%; box-shadow: 0px 4px 6px rgba(0,0,0,0.2); transition: transform 0.2s; }
        #myBtn:hover { transform: scale(1.1); }
    </style>
    <button onclick="window.parent.document.querySelector('.main').scrollTo({top:0, behavior:'smooth'})" id="myBtn">▲</button>
""", unsafe_allow_html=True)

if 'target_location' not in st.session_state: st.session_state.target_location = None
if 'analysis_result' not in st.session_state: st.session_state.analysis_result = pd.DataFrame()
if 'search_results' not in st.session_state: st.session_state.search_results = []

st.title("🏥 병원 마케팅 올인원 툴")
tab1, tab2, tab3, tab4 = st.tabs(["📊 키워드 분석 (Map)", "📝 블로거 발굴", "📺 유튜버 발굴", "📸 인스타 발굴"])

with tab1:
    st.header("1. 지도 기반 상권 분석 및 키워드 추출")
    with st.expander("🔍 병원 검색 및 위치 설정", expanded=True):
        with st.form("search_form"):
            col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
            with col1: h_query = st.text_input("병원명 입력", placeholder="예: 디아트의원 청주")
            with col2: search_btn = st.form_submit_button("병원 찾기")
        if search_btn and h_query:
            places = search_places_kakao(h_query)
            if places: st.session_state.search_results = places
            else: st.warning("검색 결과가 없습니다.")
        if st.session_state.search_results:
            st.divider()
            options = {f"{p['place_name']} ({p['address_name']})": i for i, p in enumerate(st.session_state.search_results)}
            selected_option = st.radio("분석할 병원을 선택하세요", list(options.keys()))
            if st.button("✅ 선택한 병원으로 설정"):
                target = st.session_state.search_results[options[selected_option]]
                x, y, region_1, city, gu, b_dong = get_address_details_kakao(target['address_name'])
                st.session_state.target_location = {"name": target['place_name'], "x": x, "y": y, "do": region_1, "si": city, "gu": gu, "b_dong": b_dong, "h_dong": get_admin_dong(x, y)}
                st.session_state.target_location['stations'] = get_nearby_stations(x, y)
                st.rerun()

    if st.session_state.target_location:
        loc = st.session_state.target_location
        col1, col2 = st.columns([1.2, 1])
        with col2:
            st.subheader("🗺️ 분석 구역")
            # [수정] 텍스트 말풍선(DivIcon) 기능이 제거된 깨끗한 지도
            m = folium.Map(location=[loc['y'], loc['x']], zoom_start=15)
            folium.Marker([loc['y'], loc['x']], popup=f"<b>{loc['name']}</b>", tooltip=loc['name'], icon=folium.Icon(color="red", icon="star", prefix='fa')).add_to(m)
            folium.Circle(location=[loc['y'], loc['x']], radius=1500, color='#E1306C', fill=True, fill_color='#E1306C', fill_opacity=0.1).add_to(m)
            for s in loc['stations']:
                folium.Marker([s['y'], s['x']], tooltip=f"{s['name']} (역세권)", popup=s['name'], icon=folium.Icon(color="green", icon="train", prefix="fa")).add_to(m)
            st_folium(m, height=450, width="100%")
            
            # [AI 상권 분석 리포트]
            st_names = [s['name'] for s in loc['stations']]
            st_text = ", ".join(st_names) if st_names else "도보권 내 지하철역 없음"
            dong_name = loc['h_dong'] if loc['h_dong'] else loc['b_dong']
            
            report_box = f"""
            <div style="background-color:#f0f2f6; padding:15px; border-radius:10px; border-left: 5px solid #E1306C;">
                <h4 style="margin:0 0 10px 0;">📢 AI 마케팅 상권 분석</h4>
                <ul style="margin:0; padding-left:20px;">
                    <li><b>📍 행정구역:</b> 현재 <b>{loc['si']} {loc['gu']} {dong_name}</b> 지역을 분석 중입니다.</li>
                    <li><b>🚇 교통/접근성:</b> 이 병원은 <b>{st_text}</b> 인근에 위치해 있습니다.</li>
                    <li><b>💡 전략:</b> 지역명(<b>{loc['gu']}, {dong_name}</b>)이 포함된 키워드를 최우선으로 선점하세요.</li>
                </ul>
            </div>
            """
            st.markdown(report_box, unsafe_allow_html=True)

        with col1:
            disp_addr = f"{loc['si']} {loc['gu']} {loc['b_dong']}"
            if loc['h_dong'] and loc['h_dong'] != loc['b_dong']: disp_addr += f" ({loc['h_dong']})"
            st.subheader(f"📍 {disp_addr}")
            st.write("🎯 **키워드 추출 옵션**")
            c1, c2 = st.columns(2)
            use_region = c1.checkbox("🏙️ 지역명 (시/구/동)", True)
            use_station = c2.checkbox("🚇 역세권", True)
            target_cat = st.selectbox("업종", ["피부과", "성형외과", "치과", "한의원", "정형외과", "안과", "비뇨기과", "산부인과"])
            
            if st.button("🚀 키워드 추출", type="primary", use_container_width=True):
                with st.spinner("지역 기반 정밀 분석 중..."):
                    seeds = []
                    main_keywords = []
                    clean_si = loc['si'].replace("시", "") if loc['si'] else ""
                    if use_region:
                        if clean_si: seeds.extend([f"{clean_si}{target_cat}", f"{clean_si}{target_cat}추천"])
                        if loc['gu']: seeds.extend([f"{loc['gu']}{target_cat}", f"{clean_si}{loc['gu']}{target_cat}"])
                        clean_b = re.sub(r'\d+가?', '', loc['b_dong'])
                        seeds.append(f"{clean_b}{target_cat}")
                        if loc['h_dong']: seeds.append(f"{loc['h_dong']}{target_cat}")
                    if use_station:
                        for s in loc['stations']: seeds.extend([f"{s['clean_name']}역{target_cat}", f"{s['clean_name']}{target_cat}"])
                    loc['main_keywords'] = [clean_si, loc['gu'], loc['h_dong']]
                    rankings = get_naver_expanded_rankings(seeds, target_cat, {'station': use_station}, loc)
                    if rankings: st.session_state.analysis_result = pd.DataFrame(rankings)
            
            if not st.session_state.analysis_result.empty:
                df = st.session_state.analysis_result
                st.success(f"키워드 {len(df)}개")
                for _, row in df.head(30).iterrows():
                    icon = "👑" if row['priority'] >= 100 else ("🎯" if row['priority'] >= 60 else "✅")
                    st.markdown(f"""<div style="border:1px solid #eee; padding:10px; margin-bottom:5px; border-radius:5px; display:flex; justify-content:space-between; align-items:center; background-color:{'#fff0f6' if row['priority']>=80 else 'white'};">
                        <div><b>{row['key']}</b> <span style="font-size:0.8em; color:#E1306C;">{icon}</span></div>
                        <div style="text-align:right;"><span style="font-size:0.8em; color:#666;">조회수</span><br><b>{row['total']:,}</b></div>
                    </div>""", unsafe_allow_html=True)
                st.download_button("📥 다운로드", df.to_csv(index=False).encode('utf-8-sig'), "keywords.csv", "text/csv", use_container_width=True)

with tab2:
    st.header("2. 블로거 발굴")
    with st.form("blog_form"):
        col_b1, col_b2 = st.columns([3, 1], vertical_alignment="bottom")
        with col_b1: region_input = st.text_input("타겟 지역명", placeholder="예: 청주 성안길")
        with col_b2: submit_blog = st.form_submit_button("🕵️‍♀️ 블로거 찾기")
    if submit_blog and region_input:
        with st.spinner("블로거 분석 중..."):
            items = search_bloggers(f"{region_input} 피부과 후기", 30)
            if items:
                for i in items:
                    st.write(f"- [{i['bloggername']}] {i['title'].replace('<b>','').replace('</b>','')}")
                    st.caption(f"🔗 {i['link']}")

with tab3:
    st.header("3. 유튜브")
    st.info("준비중")

with tab4:
    st.header("4. 인스타")
    st.info("준비중")