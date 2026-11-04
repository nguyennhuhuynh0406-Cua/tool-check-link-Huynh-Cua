import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io

st.set_page_config(page_title="Tool Check Link Ảnh", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ẢNH HỎNG")
st.markdown("Hỗ trợ quét từ file Excel hoặc link Google Sheet. Kết quả trả về giữ nguyên cấu trúc gốc.")

async def check_url(session, semaphore, item):
    idx, url = item
    headers = {'User-Agent': 'Mozilla/5.0'}
    async with semaphore:
        try:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=8), headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    return {'idx': idx, 'Link_lỗi': url, 'Mã_Lỗi': resp.status}
        except Exception:
            return {'idx': idx, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối / Link hỏng'}
    return None

async def process_data(df):
    tasks_list = []
    for idx, row in df.iterrows():
        for col_idx in range(len(row)):
            val = str(row.get(col_idx, ''))
            match = re.search(r'url=(https?://[^,}]+)', val)
            if match:
                tasks_list.append((idx, match.group(1).strip()))
                break

    semaphore = asyncio.Semaphore(100)
    connector = aiohttp.TCPConnector(limit=150, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_url(session, semaphore, item) for item in tasks_list]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

input_method = st.radio("1. Chọn nguồn dữ liệu:", ("Tải file Excel", "Dán link Google Sheet"))

df = None
if input_method == "Tải file Excel":
    uploaded_file = st.file_uploader("Tải file .xlsx hoặc .xls lên đây", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, header=None)
else:
    sheet_url = st.text_input("Dán link Google Sheet vào đây:")
    st.info("Lưu ý: File Google Sheet cần được cài đặt quyền chia sẻ là 'Bất kỳ ai có liên kết' (Anyone with the link).")
    if sheet_url:
        try:
            if "/edit" in sheet_url or "/view" in sheet_url:
                csv_url = re.sub(r'/(edit|view).*$', '/export?format=csv', sheet_url)
            else:
                csv_url = sheet_url
            df = pd.read_csv(csv_url, header=None)
        except Exception:
            st.error("Không thể đọc được dữ liệu. Hãy kiểm tra lại link hoặc quyền chia sẻ của Google Sheet!")

if df is not None:
    if st.button("2. BẤM VÀO ĐÂY ĐỂ QUÉT LINK", type="primary"):
        with st.spinner("Đang quét tốc độ cao, vui lòng đợi..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            error_list = loop.run_until_complete(process_data(df))
            
            if len(error_list) > 0:
                df_errors = pd.DataFrame(error_list)
                error_indices = df_errors['idx'].tolist()
                
                df_result = df.loc[error_indices].copy()
                df_result.insert(0, 'Dòng_Dữ_Liệu_Gốc', [i + 1 for i in error_indices])
                df_result['Link_bị_lỗi'] = df_errors['Link_lỗi'].values
                df_result['Mã_Lỗi'] = df_errors['Mã_Lỗi'].values
                
                st.error(f"⚠️ Phát hiện {len(error_list)} link lỗi!")
                st.dataframe(df_result)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_result.to_excel(writer, index=False)
                
                st.download_button(
                    label="3. ⬇️ TẢI FILE KẾT QUẢ VỀ MÁY",
                    data=output.getvalue(),
                    file_name="ket_qua_link_loi.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.success("🎉 Tuyệt vời, không có link ảnh nào bị hỏng!")
