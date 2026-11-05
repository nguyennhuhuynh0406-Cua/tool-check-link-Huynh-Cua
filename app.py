import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm từ văn bản, Excel hoặc Google Sheet (Quét toàn bộ các cột trong file).")

async def check_url(session, semaphore, item):
    idx, url = item
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), headers=headers, allow_redirects=True) as resp:
                if resp.status >= 400:
                    return {'idx': idx, 'Link_lỗi': url, 'Mã_Lỗi': resp.status}
        except asyncio.TimeoutError:
            return {'idx': idx, 'Link_lỗi': url, 'Mã_Lỗi': 'Timeout (Hết thời gian chờ)'}
        except Exception as e:
            return {'idx': idx, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối / Link hỏng'}
    return None

async def process_data(df):
    tasks_list = []
    url_pattern = re.compile(r'(https?://[^\s,\]}\)]+)')
    
    for idx, row in df.iterrows():
        # Quét qua tất cả các ô trong 1 dòng, không dừng lại giữa chừng
        for col_idx in range(len(row)):
            val = str(row.get(col_idx, ''))
            if 'http' in val:
                matches = url_pattern.findall(val)
                if matches:
                    for match in matches:
                        tasks_list.append((idx, match.strip()))

    if not tasks_list:
        return []

    semaphore = asyncio.Semaphore(50)
    connector = aiohttp.TCPConnector(limit=100, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_url(session, semaphore, item) for item in tasks_list]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]

input_method = st.radio("1. Chọn nguồn dữ liệu:", ("Tải file Excel", "Dán link Google Sheet", "Nhập link trực tiếp"))

df = None
if input_method == "Tải file Excel":
    uploaded_file = st.file_uploader("Tải file .xlsx hoặc .xls lên đây", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, header=None)
elif input_method == "Dán link Google Sheet":
    sheet_url = st.text_input("Dán link Google Sheet vào đây:")
    st.info("Lưu ý: File Google Sheet cần bật Share 'Bất kỳ ai có liên kết'.")
    if sheet_url:
        try:
            if "/edit" in sheet_url or "/view" in sheet_url:
                csv_url = re.sub(r'/(edit|view).*$', '/export?format=csv', sheet_url)
            else:
                csv_url = sheet_url
            df = pd.read_csv(csv_url, header=None)
        except Exception:
            st.error("Không đọc được dữ liệu. Kiểm tra lại link hoặc quyền truy cập!")
else:
    raw_text = st.text_area("Dán trực tiếp danh sách link vào đây (mỗi dòng 1 link hoặc copy nguyên đoạn văn bản chứa link lộn xộn):", height=200)
    if raw_text.strip():
        lines = [line for line in raw_text.split('\n') if line.strip()]
        df = pd.DataFrame(lines, columns=['Dữ_Liệu_Nhập_Vào'])

if df is not None:
    if st.button("2. BẤM VÀO ĐÂY ĐỂ QUÉT LINK", type="primary"):
        with st.spinner("Đang quét toàn bộ dữ liệu, vui lòng giữ nguyên trang..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            error_list = loop.run_until_complete(process_data(df))
            
            if len(error_list) > 0:
                df_errors = pd.DataFrame(error_list)
                error_indices = df_errors['idx'].tolist()
                
                df_result = df.loc[error_indices].copy()
                df_result.insert(0, 'Dòng_Gốc', [i + 1 for i in error_indices])
                df_result['Link_bị_lỗi'] = df_errors['Link_lỗi'].values
                df_result['Mã_Lỗi'] = df_errors['Mã_Lỗi'].values
                
                st.error(f"⚠️ Phát hiện {len(error_list)} link lỗi (404, 403...)!")
                st.dataframe(df_result)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_result.to_excel(writer, index=False)
                
                st.download_button(
                    label="3. ⬇️ TẢI FILE KẾT QUẢ VỀ MÁY",
                    data=output.getvalue(),
                    file_name="ket_qua_quet_toan_bo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.success("🎉 Tất cả link đều hoạt động bình thường!")
