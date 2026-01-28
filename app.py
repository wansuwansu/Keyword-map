import streamlit as st
import time
import hmac
import hashlib
import base64
import requests

# API 키 설정 (검증된 키 유지)
KAKAO_REST_KEY = "968344aed4aff4d7aeb37eb199767d5a"
AD_API_KEY = "01000000002855c92d066a6e30d3eaeafbe6adebd688d73c3dd901f151b52c430ddcad5c88"
AD_SECRET_KEY = "AQAAAAAoVcktBmpuMNPq6vvmrevWXrbXSbEoh/+/3U3vTcTLyA=="
AD_CUSTOMER_ID = "4173931"

def get_location_info(query):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    try:
        res = requests.get(url, params={"query": query, "size": 1}, headers=headers)
        if res.status_code == 200:
            data = res.json()
            if data['documents']:
                place = data['documents'][0]
                addr = place['address_name']
                parts = addr.split()
                # 시/구/동 정보 추출
                si = next((p for p in parts if p.endswith('시')), "")
                gu = next((p for p in parts if p.endswith('구')), "")
                dong = next((p for p in parts if p.endswith('동')), "")
                return {"full_addr": addr, "si": si, "gu": gu, "dong": dong}, "성공"
        return None, "위치를 찾을 수 없습니다."
    except:
        return None, "카카오 연결 실패"

def get_naver_rankings(keywords):
    uri = '/keywordstool'
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}.GET.{uri}"
    signature = base64.b64encode(hmac.new(bytes(AD_SECRET_KEY, 'UTF-8'), bytes(msg, 'UTF-8'), hashlib.sha256).digest())
    headers = {'X-Timestamp': timestamp, 'X-API-KEY': AD_API_KEY, 'X-Customer': AD_CUSTOMER_ID, 'X-Signature': signature}
    clean_ks = list(set([k.replace(" ", "") for k in keywords]))[:5]
    res = requests.get("https://api.naver.com" + uri, params={'hintKeywords': ','.join(clean_ks), 'showDetail': '1'}, headers=headers)
    if res.status_code == 200:
        data = res.json()
        results = []
        for item in data['keywordList']:
            if item['relKeyword'].replace(" ", "") in clean_ks:
                p = 5 if isinstance(item['monthlyPcQcCnt'], str) else item['monthlyPcQcCnt']
                m = 5 if isinstance(item['monthlyMobileQcCnt'], str) else item['monthlyMobileQcCnt']
                results.append({'key': item['relKeyword'], 'total': p + m, 'mobile': m})
        return results
    return []

st.title("🏥 실전 지역 키워드 분석기")

with st.form("search_form"):
    h_input = st.text_input("병원명 + 지점명", placeholder="예: 바노바기 대전")
    category = st.text_input("진료 과목", value="피부과")
    submit = st.form_submit_button("🚀 분석 시작")

if submit:
    if h_input:
        with st.spinner("📍 위치 분석 중..."):
            loc, msg = get_location_info(h_input)
            if loc:
                st.success(f"✅ 확인된 주소: {loc['full_addr']}")
                gu, dong = loc['gu'], loc['dong']
                short_dong = dong.replace("동", "")

                # 키워드 조합 로직 개선 (의미 없는 한 글자 제거)
                k_list = [f"{dong}{category}", f"{short_dong}{category}"]
                if len(short_dong) > 1:
                    k_list.append(f"{short_dong}역{category}")
                
                # 구 단위는 '구'를 붙여서 검색 (예: 서구피부과)
                if gu:
                    k_list.append(f"{gu}{category}")
                
                # '대전피부과' 같은 대형 키워드 추가 (지역 기반)
                if loc['si']:
                    k_list.append(f"{loc['si']}{category}".replace("광역시", ""))

                with st.spinner("📊 데이터 불러오는 중..."):
                    rankings = get_naver_rankings(k_list)
                    if rankings:
                        top_sorted = sorted(rankings, key=lambda x: x['total'], reverse=True)
                        st.subheader(f"🏆 {dong or gu} 지역 베스트 키워드")
                        for i, r in enumerate(top_sorted[:5], 1):
                            st.info(f"**{i}위. {r['key']}** (월간 {r['total']:,}회)")