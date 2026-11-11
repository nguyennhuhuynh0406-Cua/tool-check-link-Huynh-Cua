import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io
import gc

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG của Huỳnh Cua")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm từ văn bản, Excel hoặc Google Sheet. **(Bản Tối Ưu RAM Khủng - Quét Cuốn Chiếu)**")

def get_excel_col_name(n):
    result = ""
    n += 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

async def check_url(session, semaphore, item):
    idx, col_letter, url = item
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'vi-VN,vi;q=0.9',
        'Referer': 'https://www.dienmayxanh.com/',
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
        'Connection': 'keep-alive'
    }
    max_retries = 3
    async with semaphore:
        await asyncio.sleep(0.05) 
        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        if resp.status in [403, 429, 500, 502, 503, 504] and attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': str(resp.status)}
                    return None
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Timeout'}
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối'}
    return None

async def process_data(df, progress_bar, status_text):
    url_pattern = re.compile(r'https?://[^\s,"\'<>\]}]+')
    total_rows = len(df)
    results = []
    
    status_text.text("🚀 Khởi động động cơ quét cuốn chiếu (Siêu tối ưu RAM)...")
    
    semaphore = asyncio.Semaphore(100) 
    connector = aiohttp.TCPConnector(limit=150, ssl=False)
    
    row_batch_size = 500 # Cắt dữ liệu ra xử lý từng 500 dòng một
    total_links_processed = 0
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, total_rows, row_batch_size):
            df_batch = df.iloc[i:i+row_batch_size]
            tasks_list = []
            
            # Chỉ trích xuất link của 500 dòng hiện tại
            for idx, row in df_batch.iterrows():
                for col_idx, col_name in enumerate(df_batch.columns):
                    val = str(row.get(col_name, ''))
                    if 'http' in val:
                        matches = url_pattern.findall(val)
                        if matches:
                            col_letter = get_excel_col_name(col_idx)
                            for match in set(matches):
                                clean_link = match.strip(".'\"\\,;>)]}")
                                if clean_link:
                                    tasks_list.append((idx, col_letter, clean_link))
            
            if tasks_list:
                tasks = [check_url(session, semaphore, item) for item in tasks_list]
                chunk_results = await asyncio.gather(*tasks)
                results.extend([r for r in chunk_results if r is not None])
                total_links_processed += len(tasks_list)
            
            # Tính phần trăm theo tiến độ DÒNG EXCEL để trình duyệt web không bị ngắt kết nối
            current_processed_rows = min(i + row_batch_size, total_rows)
            progress = current_processed_rows / total_rows
            progress_bar.progress(progress)
            status_text.text(f"⏳ Đang quét cuốn chiếu: Xong {current_processed_rows}/{total_rows} dòng (đã check {total_links_processed} link)...")
            
            # Dọn sạch sành sanh bộ nhớ sau mỗi 500 dòng
            del df_batch
            if tasks_list:
                del tasks
                del chunk_results
            gc.collect()
            
    status_text.text(f"🎉 Hoàn thành! Đã quét tổng cộng {total_links_processed} link trong {total_rows} dòng.")
    return results

input_method = st.radio("1. Chọn nguồn dữ liệu:", ("Tải file Excel", "Dán link Google Sheet", "Nhập link trực tiếp"))

df = None
if input_method == "Tải file Excel":
    uploaded_file = st.file_uploader("Tải file .xlsx hoặc .xls lên đây", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, header=None, dtype=str)
elif input_method == "Dán link Google Sheet":
    sheet_url = st.text_input("Dán link Google Sheet vào đây:")
    st.info("Lưu ý: File Google Sheet cần bật Share 'Bất kỳ ai có liên kết'.")
    if sheet_url:
        try:
            gid_match = re.search(r'gid=(\d+)', sheet_url)
            if "/edit" in sheet_url or "/view" in sheet_url:
                csv_url = re.sub(r'/(edit|view).*$', '/export?format=csv', sheet_url)
                if gid_match:
                    csv_url += f"&gid={gid_match.group(1)}"
            else:
                csv_url = sheet_url
            df = pd.read_csv(csv_url, header=None, dtype=str)
        except Exception:
            st.error("Không đọc được dữ liệu. Kiểm tra lại link hoặc quyền truy cập!")
else:
    raw_text = st.text_area("Dán trực tiếp danh sách link vào đây:", height=200)
    if raw_text.strip():
        lines = [line for line in raw_text.split('\n') if line.strip()]
        df = pd.DataFrame(lines, columns=['Dữ_Liệu_Nhập_Vào'])

if df is not None:
    st.success(f"✅ Tải dữ liệu thành công! Tổng cộng file có {len(df)} dòng dữ liệu.")
    
    st.warning("⚠️ LƯU Ý: Quét 260.000 link sẽ mất khoảng 20 - 30 phút. Thanh trạng thái sẽ liên tục chạy số dòng để báo cho bạn biết hệ thống vẫn đang sống.")
    
    if st.button("2. 🚀 BẤM VÀO ĐÂY ĐỂ QUÉT TOÀN BỘ FILE (1 LẦN DUY NHẤT)", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        error_list = loop.run_until_complete(process_data(df, progress_bar, status_text))
        
        if len(error_list) > 0:
            error_indices = sorted(list(set([e['idx'] for e in error_list])))
            df_result = df.loc[error_indices].copy()
            df_result.insert(0, 'Dòng_Gốc', [i + 1 for i in df_result.index])
            
            error_cols_found = sorted(list(set([e['col_letter'] for e in error_list])))
            
            for col in error_cols_found:
                df_result[f'Link_Lỗi_(Cột_{col})'] = ""
                df_result[f'Mã_Lỗi_(Cột_{col})'] = ""
            
            for e in error_list:
                r_idx = e['idx']
                c_name = e['col_letter']
                
                current_link = df_result.at[r_idx, f'Link_Lỗi_(Cột_{c_name})']
                if current_link:
                    df_result.at[r_idx, f'Link_Lỗi_(Cột_{c_name})'] = f"{current_link}\n{e['Link_lỗi']}"
                    df_result.at[r_idx, f'Mã_Lỗi_(Cột_{c_name})'] = f"{df_result.at[r_idx, f'Mã_Lỗi_(Cột_{c_name})']}\n{e['Mã_Lỗi']}"
                else:
                    df_result.at[r_idx, f'Link_Lỗi_(Cột_{c_name})'] = e['Link_lỗi']
                    df_result.at[r_idx, f'Mã_Lỗi_(Cột_{c_name})'] = e['Mã_Lỗi']
            
            st.error(f"⚠️ Đã quét xong! Phát hiện tổng cộng {len(error_list)} link lỗi trong toàn bộ file.")
            st.dataframe(df_result)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_result.to_excel(writer, index=False)
            
            st.download_button(
                label="3. ⬇️ TẢI FILE KẾT QUẢ GỘP VỀ MÁY",
                data=output.getvalue(),
                file_name="ket_qua_quet_FULL_toan_bo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.success("🎉 Thật tuyệt vời! Toàn bộ link trong file của bạn đều sống 100%!")
