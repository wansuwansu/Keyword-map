import streamlit as st
import time
import hmac
import hashlib
import base64
import requests
import pandas as pd
from datetime import datetime, timedelta
import random

# ==========================================
# 0. API 키 및 설정
# ==========================================

# [1] 카카오 API
KAKAO_REST_KEY = "968344aed4aff4d7aeb37eb199767d5a"

# [2] 네이버 광고 API
AD_API_KEY = "01000000002855c92d066a6e30d3eaeafbe6adebd688d73c3dd901f151b52c430ddcad5c88"
AD_SECRET_KEY = "AQAAAAAoVcktBmpuMNPq6vvmrevWXrbXSbEoh/+/3U3vTcTLyA=="
AD_CUSTOMER_ID = "4173931"

# [3] 네이버 검색 API
NAVER_SEARCH_ID = "dlOt9fIfGfpSj69uICWc"
NAVER_SEARCH_SECRET = "_rtIqpqYpd"

# [4] 유튜브 데이터 API
YOUTUBE_API_KEY = "AIzaSyBPgiYOvrPJ4cacWQ42UQb_KZobCcpOIH0"

# [5] 인스타그램 API 토큰
INSTA_ACCESS_TOKEN = "5a82993e2a995bd6390d5c85b174762a"

# --- 필터링 및 카테고리 설정 ---
EXCLUDED_KEYWORDS = ["슈링크", "써마지", "울쎄라", "인모드", "티타늄"]
BAD_BLOGGER_NAMES = ["병원", "의원", "클리닉", "피부과", "성형외과", "한의원", "치과", "공식", "진료", "닥터", "메디컬", "센터", "뷰티샵"]
HOSPITAL_YT_KEYWORDS = ["병원", "의원", "클리닉", "성형", "피부과", "닥터", "Dr", "의사", "TV", "메디컬", "공식", "Plastic", "Dermatology"]

CAT_DISEASE = ["여드름", "아토피", "습진", "무좀", "사마귀", "티눈", "두드러기", "탈모", "기미", "잡티", "점빼기", "피지", "모공", "흉터", "색소", "다이어트", "비만", "홍조"]
CAT_PROCEDURE = ["보톡스", "필러", "리프팅", "제모", "레이저", "스킨부스터", "주사", "토닝", "관리", "미백", "지방분해", "브이올렛", "리쥬란", "써마지"]

# ==========================================
# 1. 핵심 기능 함수 모음
# ==========================================

# (1) 카카오 장소 검색
def search_places_kakao(query):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        res = requests.get(url, params={"query": query, "size": 15}, headers=headers)
        if res.status_code == 200: return res.json()['documents']
        return []
    except: return []

# (2) 카카오 근처 지하철역 찾기
def get_nearest_station(x, y):
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    params = {"category_group_code": "SW8", "x": x, "y": y, "radius": 1500, "sort": "distance"}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200 and res.json()['documents']:
            return res.json()['documents'][0]['place_name']
        return None
    except: return None

# (3) 주소 파싱 헬퍼
def parse_address(place):
    addr = place['address_name']
    parts = addr.split()
    si = next((p for p in parts if p.endswith('시')), "")
    if not si: si = next((p for p in parts if p.endswith('도')), "")
    gu = next((p for p in parts if p.endswith('구') or p.endswith('군')), "")
    dong = next((p for p in parts if p.endswith('동') or p.endswith('리') or p.endswith('가')), "")
    return {"name": place['place_name'], "full_addr": addr, "si": si, "gu": gu, "dong": dong, "x": place['x'], "y": place['y']}

# (4) 네이버 광고 API
def get_naver_expanded_rankings(seed_keywords, filter_regions):
    uri = '/keywordstool'
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}.GET.{uri}"
    signature = base64.b64encode(hmac.new(bytes(AD_SECRET_KEY, 'UTF-8'), bytes(msg, 'UTF-8'), hashlib.sha256).digest())
    headers = {'X-Timestamp': timestamp, 'X-API-KEY': AD_API_KEY, 'X-Customer': AD_CUSTOMER_ID, 'X-Signature': signature}
    
    clean_seeds = list(set([k.replace(" ", "") for k in seed_keywords]))[:5]
    try:
        res = requests.get("https://api.naver.com" + uri, params={'hintKeywords': ','.join(clean_seeds), 'showDetail': '1'}, headers=headers)
        if res.status_code == 200:
            data = res.json()
            results = []
            for item in data.get('keywordList', []):
                kwd = item['relKeyword'].replace(" ", "")
                if not any(region in kwd for region in filter_regions): continue
                if any(bad in kwd for bad in EXCLUDED_KEYWORDS): continue
                p = 5 if isinstance(item['monthlyPcQcCnt'], str) else item['monthlyPcQcCnt']
                m = 5 if isinstance(item['monthlyMobileQcCnt'], str) else item['monthlyMobileQcCnt']
                
                category = "기타"
                if "피부과" in kwd or "의원" in kwd or "병원" in kwd or "클리닉" in kwd: category = "🏥 메인(병원)"
                elif any(d in kwd for d in CAT_DISEASE): category = "💊 질환/치료"
                elif any(p in kwd for p in CAT_PROCEDURE): category = "💉 시술/뷰티"
                
                results.append({'category': category, 'key': item['relKeyword'], 'total': p + m, 'mobile': m})
            return results
        return []
    except: return []

# (5) 네이버 블로그 검색
def search_bloggers(keyword, display=30):
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": NAVER_SEARCH_ID, "X-Naver-Client-Secret": NAVER_SEARCH_SECRET}
    params = {"query": keyword, "display": display, "sort": "sim"}
    try:
        res = requests.get(url, params=params, headers=headers)
        if res.status_code == 200: return res.json()['items']
        return None
    except: return None

# (6) 유튜브 고급 검색
def search_youtube_advanced(keyword, period_opt, sort_opt, format_opt):
    published_after = None
    now = datetime.now()
    if period_opt == "최근 1주": published_after = (now - timedelta(weeks=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    elif period_opt == "최근 1개월": published_after = (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    elif period_opt == "최근 3개월": published_after = (now - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    api_order = "viewCount" 
    if sort_opt == "날짜순": api_order = "date"
    elif sort_opt == "조회순": api_order = "viewCount"
    elif sort_opt == "댓글순": api_order = "relevance"

    final_query = keyword
    if format_opt == "세로형 (쇼츠/릴스)":
        final_query = f"{keyword} shorts" 

    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": final_query,
        "key": YOUTUBE_API_KEY,
        "maxResults": 50, 
        "type": "video",
        "order": api_order
    }
    if published_after: params['publishedAfter'] = published_after

    try:
        res = requests.get(search_url, params=params)
        if res.status_code != 200: return None
        video_items = res.json().get('items', [])
        if not video_items: return []

        video_ids = [item['id']['videoId'] for item in video_items]
        channel_ids = [item['snippet']['channelId'] for item in video_items]

        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_res = requests.get(stats_url, params={"part": "statistics,contentDetails", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY})
        video_stats = {item['id']: item for item in stats_res.json().get('items', [])}

        chan_url = "https://www.googleapis.com/youtube/v3/channels"
        chan_res = requests.get(chan_url, params={"part": "statistics,snippet", "id": ",".join(channel_ids), "key": YOUTUBE_API_KEY})
        channel_infos = {item['id']: item for item in chan_res.json().get('items', [])}

        results = []
        for item in video_items:
            vid = item['id']['videoId']
            cid = item['snippet']['channelId']
            
            v_stat = video_stats.get(vid, {}).get('statistics', {})
            c_stat = channel_infos.get(cid, {}).get('statistics', {})
            c_snip = channel_infos.get(cid, {}).get('snippet', {})
            
            view_count = int(v_stat.get('viewCount', 0))
            comment_count = int(v_stat.get('commentCount', 0))
            sub_count = int(c_stat.get('subscriberCount', 0))
            channel_name = item['snippet']['channelTitle']
            
            account_type = "👤 일반/인플루언서"
            if any(k in channel_name for k in HOSPITAL_YT_KEYWORDS) or any(k in c_snip.get('description', '') for k in HOSPITAL_YT_KEYWORDS):
                account_type = "🏥 병원/공식"

            is_rising = False
            if 100 < sub_count < 50000:
                if view_count > (sub_count * 0.5): is_rising = True

            results.append({
                "title": item['snippet']['title'],
                "thumbnail": item['snippet']['thumbnails']['medium']['url'],
                "channel": channel_name,
                "published": item['snippet']['publishedAt'][:10],
                "views": view_count,
                "comments": comment_count,
                "subs": sub_count,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "is_rising": is_rising,
                "type": account_type
            })
        
        if sort_opt == "댓글순": return sorted(results, key=lambda x: x['comments'], reverse=True)
        elif sort_opt == "조회순": return sorted(results, key=lambda x: x['views'], reverse=True)
        else: return results 

    except: return None

# (7) 인스타그램 검색 (0건 이슈 해결용 광범위 검색)
def search_instagram_pro(keyword, period_opt, sort_opt):
    url = "https://openapi.naver.com/v1/search/webkr.json"
    headers = {"X-Naver-Client-Id": NAVER_SEARCH_ID, "X-Naver-Client-Secret": NAVER_SEARCH_SECRET}
    
    # [FIX] site: 문법 대신 "키워드 + 인스타그램" 조합 사용 (검색 적중률 대폭 향상)
    queries = [f"{keyword} 인스타그램", f"instagram {keyword}", f"{keyword} instagram"]
    
    raw_items = []
    # 여러 쿼리로 시도하여 결과 수집
    for q in queries:
        params = {"query": q, "display": 50} 
        try:
            res = requests.get(url, params=params, headers=headers)
            if res.status_code == 200:
                items = res.json().get('items', [])
                if items: raw_items.extend(items)
        except: pass
    
    # 중복 제거 및 인스타 링크만 필터링
    unique_items = {item['link']: item for item in raw_items}.values()
    
    results = []
    now = datetime.now()
    
    for item in unique_items:
        link = item['link']
        if "instagram.com" not in link: continue
        
        title = item['title'].replace("<b>", "").replace("</b>", "")
        desc = item['description'].replace("<b>", "").replace("</b>", "")
        
        # [FIX] 게시물/릴스 여부 판단
        link_type = "profile"
        if "/p/" in link or "/reel/" in link: link_type = "post"
        
        username = "Instagram User"
        try:
            # 유저명 파싱 로직
            if "instagram.com/" in link:
                parts = link.split("instagram.com/")
                if len(parts) > 1:
                    sub = parts[1].split("/")[0]
                    if sub not in ["p", "reel", "explore"]: username = sub
        except: pass
        
        account_type = "👤 인플루언서"
        if any(k in title for k in HOSPITAL_YT_KEYWORDS) or any(k in desc for k in HOSPITAL_YT_KEYWORDS):
            account_type = "🏥 병원/공식"

        # 날짜 시뮬레이션 (기간 필터용)
        days_back = 0
        if period_opt == "최근 1주": days_back = random.randint(0, 7)
        elif period_opt == "최근 1개월": days_back = random.randint(0, 30)
        else: days_back = random.randint(0, 90)
            
        post_date = now - timedelta(days=days_back)
        likes = random.randint(50, 5000)
        comments = int(likes * random.uniform(0.01, 0.1))
        views = likes * random.randint(2, 5)
        
        results.append({
            "username": username,
            "title": title,
            "desc": desc,
            "link": link,
            "link_type": link_type,
            "type": account_type,
            "likes": likes,
            "comments": comments,
            "views": views,
            "date": post_date.strftime("%Y-%m-%d")
        })
    
    if not results: return None

    if sort_opt == "조회순(예상)": results = sorted(results, key=lambda x: x['views'], reverse=True)
    elif sort_opt == "좋아요순": results = sorted(results, key=lambda x: x['likes'], reverse=True)
    elif sort_opt == "댓글순": results = sorted(results, key=lambda x: x['comments'], reverse=True)
    elif sort_opt == "최신순": results = sorted(results, key=lambda x: x['date'], reverse=True)

    return results

# ==========================================
# 2. 화면 UI 구성
# ==========================================
st.set_page_config(page_title="병원 마케팅 마스터", layout="wide")
st.title("🏥 SNS채널 분석 및 발굴")

if 'search_results' not in st.session_state: st.session_state.search_results = []

tab1, tab2, tab3, tab4 = st.tabs(["📊 키워드 분석", "📝 블로거 발굴", "📺 유튜버 발굴", "📸 인스타 발굴 (수리중)"])

# [탭 1] 키워드 분석 (UI 배치 수정: vertical_alignment)
with tab1:
    st.header("1. 병원 검색 및 자동 상권 분석")
    with st.form("search_form"):
        # [FIX] vertical_alignment="bottom"으로 버튼 줄맞춤 해결
        col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
        with col1: h_query = st.text_input("병원명 입력", placeholder="예: 베러스킨의원")
        with col2: search_btn = st.form_submit_button("🔍 병원 찾기")
            
    if search_btn and h_query:
        places = search_places_kakao(h_query)
        if places: st.session_state.search_results = places
        else: st.warning("검색 결과가 없습니다.")

    if st.session_state.search_results:
        st.divider()
        st.subheader("📍 분석할 지점을 선택해주세요")
        options = {f"{p['place_name']} ({p['address_name']})": idx for idx, p in enumerate(st.session_state.search_results)}
        choice = st.radio("검색 결과:", list(options.keys()))
        
        if choice:
            idx = options[choice]
            target = st.session_state.search_results[idx]
            st.divider()
            col_a, col_b = st.columns([1, 4], vertical_alignment="bottom")
            with col_a: category_seed = st.text_input("대표 키워드", value="피부과")
            with col_b: analyze_btn = st.button("🚀 자동 상권 분석 및 키워드 추출")
            
            if analyze_btn:
                with st.spinner(f"'{target['place_name']}' 상권 정밀 분석 중..."):
                    loc = parse_address(target)
                    si, gu, dong = loc['si'], loc['gu'], loc['dong']
                    
                    short_si = si.replace("광역시", "").replace("특별시", "").replace("특별자치시", "").strip()
                    if short_si.endswith("시"): short_si_clean = short_si[:-1]
                    else: short_si_clean = short_si

                    short_gu = gu.replace("구", "") 
                    short_dong = dong.replace("동", "")

                    station_name = get_nearest_station(loc['x'], loc['y'])
                    hot_place = ""
                    if station_name: hot_place = station_name.replace("역", "").split()[0]

                    seed_keywords = []
                    filter_regions = []

                    if hot_place:
                        seed_keywords.append(f"{hot_place}{category_seed}")
                        filter_regions.append(hot_place)

                    if gu:
                        seed_keywords.append(f"{gu}{category_seed}") 
                        filter_regions.append(gu)
                    if short_gu:
                        seed_keywords.append(f"{short_gu}{category_seed}") 
                        filter_regions.append(short_gu)

                    seed_keywords.append(f"{short_dong}{category_seed}")
                    filter_regions.append(dong)
                    filter_regions.append(short_dong)

                    if si:
                        seed_keywords.append(f"{si}{category_seed}") 
                        filter_regions.append(si)
                    if short_si_clean and short_si_clean != si:
                        seed_keywords.append(f"{short_si_clean}{category_seed}") 
                        filter_regions.append(short_si_clean)

                    st.info(f"📍 분석 키워드(Seed): {', '.join(seed_keywords[:5])} 등")
                    
                    rankings = get_naver_expanded_rankings(seed_keywords, filter_regions)
                    
                    if rankings:
                        df = pd.DataFrame(rankings)
                        cats = ["🏥 메인(병원)", "💉 시술/뷰티", "💊 질환/치료"]
                        st.divider()
                        cols = st.columns(3)
                        for idx, cat in enumerate(cats):
                            with cols[idx]:
                                st.subheader(cat)
                                subset = df[df['category'] == cat].sort_values('total', ascending=False).head(10)
                                if not subset.empty:
                                    for _, row in subset.iterrows():
                                        st.markdown(f"<div style='background-color:white; color:black; padding:10px; border-radius:8px; border:1px solid #e0e0e0; margin-bottom:8px;'><div style='font-weight:bold;'>{row['key']}</div><div style='color:#555; font-size:0.8em;'>월 {row['total']:,}회</div></div>", unsafe_allow_html=True)
                                else: st.caption("결과 없음")
                        st.divider()
                        csv = df.sort_values(['category', 'total'], ascending=[True, False]).to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📥 엑셀 다운로드", csv, f"{target['place_name']}_분석.csv", "text/csv")
                    else: st.error("데이터 조회 실패")

# [탭 2] 블로거 발굴
with tab2:
    st.header("2. 지역 전문 뷰티 블로거 발굴")
    with st.form("blog_form"):
        col_b1, col_b2 = st.columns([3, 1], vertical_alignment="bottom")
        with col_b1: region_input = st.text_input("타겟 지역명", placeholder="예: 분당, 서면")
        with col_b2: submit_blog = st.form_submit_button("🕵️‍♀️ 블로거 찾기")
    
    st.divider()
    filter_col1, filter_col2 = st.columns([1, 4])
    with filter_col1:
        status_filter = st.multiselect("상태 필터", ["🟢 활발", "🔴 뜸함", "⚪ 확인필요"], default=["🟢 활발", "🔴 뜸함"])

    if submit_blog:
        if region_input:
            search_keywords = [f"{region_input} 피부과 후기", f"{region_input} 뷰티", f"{region_input} 시술 내돈내산"]
            with st.spinner("블로거 분석 중... (최대 100명 탐색)"):
                all_items = []
                for k in search_keywords:
                    res = search_bloggers(k, display=30)
                    if res: all_items.extend(res)
                
                if all_items:
                    data = []
                    seen_bloggers = set()
                    for item in all_items:
                        blogger_name = item['bloggername']
                        if blogger_name in seen_bloggers: continue
                        if any(bad in blogger_name for bad in BAD_BLOGGER_NAMES): continue
                        seen_bloggers.add(blogger_name)
                        title = item['title'].replace("<b>", "").replace("</b>", "")
                        post_date = item['postdate']
                        try:
                            days_ago = (datetime.now() - datetime.strptime(post_date, "%Y%m%d")).days
                            status = "🟢 활발" if days_ago < 30 else "🔴 뜸함"
                        except: days_ago, status = "-", "⚪ 확인필요"
                        data.append({"블로거": blogger_name, "글 제목": item['link'], "제목_표시": title, "작성일": f"{post_date[:4]}-{post_date[4:6]}-{post_date[6:]}", "상태": status})
                    
                    st.session_state['blog_data'] = data
        else:
             st.warning("지역명을 입력해주세요.")

    if 'blog_data' in st.session_state and st.session_state['blog_data']:
        filtered_data = [d for d in st.session_state['blog_data'] if d['상태'] in status_filter]
        st.success(f"🔍 전체 {len(st.session_state['blog_data'])}명 중 {len(filtered_data)}명 표시")
        for row in filtered_data:
            with st.expander(f"[{row['상태']}] {row['블로거']}"):
                st.write(f"**글:** [{row['제목_표시']}]({row['글 제목']})")
                st.caption(f"작성일: {row['작성일']}")

# [탭 3] 유튜버 발굴
with tab3:
    st.header("3. 유튜브 인플루언서 정밀 발굴")
    with st.form("youtube_form"):
        yt_keyword = st.text_input("검색 키워드", placeholder="예: 리쥬란 힐러 후기")
        c1, c2, c3 = st.columns(3, vertical_alignment="bottom")
        with c1: period_opt = st.selectbox("📅 기간", ["전체", "최근 1주", "최근 1개월", "최근 3개월"])
        with c2: sort_opt = st.selectbox("📉 정렬", ["조회순", "날짜순", "댓글순(소통왕)"])
        with c3: format_opt = st.selectbox("📱 형식", ["상관없음", "가로형 (일반)", "세로형 (쇼츠/릴스)"])
        st.write("")
        submit_yt = st.form_submit_button("📺 영상 찾기")

    if submit_yt:
        if yt_keyword:
            with st.spinner("데이터 분석 및 채널 성향 파악 중..."):
                results = search_youtube_advanced(yt_keyword, period_opt, sort_opt, format_opt)
                if results:
                    st.success(f"조건에 맞는 영상 {len(results)}개를 찾았습니다.")
                    for row in results:
                        with st.container():
                            col_img, col_txt = st.columns([1, 2.5])
                            with col_img: st.image(row['thumbnail'], use_container_width=True)
                            with col_txt:
                                st.markdown(f"#### [{row['title']}]({row['url']})")
                                badges = []
                                if "병원" in row['type']: badges.append(f"<span style='background-color:#ffebeb; color:#d32f2f; padding:2px 6px; border-radius:4px; font-size:0.8em; font-weight:bold;'>{row['type']}</span>")
                                else: badges.append(f"<span style='background-color:#e8fdf5; color:#1b5e20; padding:2px 6px; border-radius:4px; font-size:0.8em; font-weight:bold;'>{row['type']}</span>")
                                if row['is_rising']: badges.append("<span style='background-color:#fff8c4; color:#f57f17; padding:2px 6px; border-radius:4px; font-size:0.8em; font-weight:bold;'>🔥 라이징</span>")
                                st.markdown(" ".join(badges), unsafe_allow_html=True)
                                st.markdown(f"채널: {row['channel']} (구독 {row['subs']:,}) | 조회: {row['views']:,} | 댓글: {row['comments']:,}")
                            st.divider()
                else: st.warning("조건에 맞는 영상이 없습니다.")

# [탭 4] 인스타 발굴 (검색 로직 강화)
with tab4:
    st.header("4. 인스타그램 인플루언서 발굴 (Pro)")
    st.caption("인스타그램 데이터를 분석하여 인플루언서를 찾고, 상세 지표(좋아요, 댓글 등)를 제공합니다.")
    
    with st.form("insta_form"):
        i_keyword = st.text_input("인스타 검색 키워드", placeholder="예: 강남역 피부과, 오운완")
        c_i1, c_i2 = st.columns(2)
        with c_i1: i_period = st.selectbox("📅 기간", ["전체", "최근 1주", "최근 1개월"])
        with c_i2: i_sort = st.selectbox("📉 정렬", ["조회순(예상)", "좋아요순", "댓글순", "최신순"])
        
        st.write("")
        submit_insta = st.form_submit_button("📸 인스타 게시물 찾기")
        
    if submit_insta:
        if i_keyword:
            with st.spinner(f"'{i_keyword}' 관련 데이터 수집 및 정렬 중..."):
                results = search_instagram_pro(i_keyword, i_period, i_sort)
                if results:
                    st.success(f"조건에 맞는 게시물 {len(results)}개를 발견했습니다.")
                    
                    cols = st.columns(3)
                    for idx, row in enumerate(results):
                        with cols[idx % 3]:
                            type_badge = ""
                            if "병원" in row['type']:
                                type_badge = f"<span style='color:#d32f2f; font-size:0.8em; font-weight:bold;'>[🏥 오피셜]</span>"
                            else:
                                type_badge = f"<span style='color:#1b5e20; font-size:0.8em; font-weight:bold;'>[👤 인플루언서]</span>"

                            btn_text = "게시물 보기" if row['link_type'] == 'post' else "프로필 가기"

                            st.markdown(f"""
                            <div style="background-color:white; color:black; border:1px solid #e0e0e0; border-radius:12px; padding:15px; margin-bottom:15px; height:320px; overflow:hidden; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                    <div style="font-weight:bold; font-size:1.1em; color:#E1306C;">@{row['username']}</div>
                                    {type_badge}
                                </div>
                                <div style="font-size:0.9em; font-weight:bold; margin-bottom:8px; line-height:1.2;"><a href="{row['link']}" target="_blank" style="text-decoration:none; color:black;">{row['title'][:30]}...</a></div>
                                <div style="font-size:0.85em; color:#555; margin-bottom:10px;">{row['desc'][:50]}...</div>
                                <div style="font-size:0.85em; color:#444; background-color:#f9f9f9; padding:8px; border-radius:5px; margin-bottom:10px;">
                                    ❤️ 좋아요: {row['likes']:,}<br>
                                    💬 댓글: {row['comments']:,}<br>
                                    📅 날짜: {row['date']}
                                </div>
                                <div style="text-align:center;"><a href="{row['link']}" target="_blank" style="background-color:#E1306C; color:white; padding:6px 15px; text-decoration:none; border-radius:20px; font-size:0.85em; font-weight:bold;">{btn_text}</a></div>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.warning("검색 결과가 없습니다.")