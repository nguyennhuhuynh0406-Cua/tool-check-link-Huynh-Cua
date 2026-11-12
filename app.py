import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io
import gc
import json
import os

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG của Huỳnh Cua")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm. **(Bản Lưu Ổ Cứng - Phục Hồi Dữ Liệu & Chống Văng Web)**")

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
        'Referer': 'https://www.dienmayxanh.com/',
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
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối / Timeout'}
    return None

# ================= CƠ CHẾ LƯU Ổ CỨNG =================
BACKUP_FILE = "ket_qua_loi.json"
STATE_FILE = "dong_hien_tai.txt"

def load_progress():
    if os.path.exists(BACKUP_FILE) and os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            row = int(f.read().strip())
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            errors = json.load(f)
        return row, errors
    return 0, []

def save_progress(row, errors):
    with open(STATE_FILE, 'w') as f:
        f.write(str(row))
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(errors, f, ensure_ascii=False)

def clear_progress():
    if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)

if 'is_scanning' not in st.session_state:
    st.session_state.is_scanning = False
if 'current_row' not in st.session_state:
    saved_row, saved_errors = load_progress()
    st.session_state.current_row = saved_row
    st.session_state.error_results = saved_errors
if 'total_links_scanned' not in st.session_state:
    st.session_state.total_links_scanned = 0
if 'df' not in st.session_state:
    st.session_state.df = None

if not st.session_state.is_scanning and st.session_state.df is None:
    input_method = st.radio("1. Chọn nguồn dữ liệu:", ("Tải file Excel", "Dán link Google Sheet", "Nhập link trực tiếp"))
    df_temp = None
    
    if input_method == "Tải file Excel":
        uploaded_file = st.file_uploader("Tải file .xlsx hoặc .xls lên đây", type=['xlsx', 'xls'])
        if uploaded_file is not None:
            df_temp = pd.read_excel(uploaded_file, header=None, dtype=str)
    elif input_method == "Dán link Google Sheet":
        sheet_url = st.text_input("Dán link Google Sheet vào đây:")
        if sheet_url:
            try:
                gid_match = re.search(r'gid=(\d+)', sheet_url)
                if "/edit" in sheet_url or "/view" in sheet_url:
                    csv_url = re.sub(r'/(edit|view).*$', '/export?format=csv', sheet_url)
                    if gid_match:
                        csv_url += f"&gid={gid_match.group(1)}"
                else:
                    csv_url = sheet_url
                df_temp = pd.read_csv(csv_url, header=None, dtype=str)
            except Exception:
                st.error("Không đọc được dữ liệu. Kiểm tra lại link!")
    else:
        raw_text = st.text_area("Dán trực tiếp danh sách link vào đây:", height=200)
        if raw_text.strip():
            lines = [line for line in raw_text.split('\n') if line.strip()]
            df_temp = pd.DataFrame(lines, columns=['Dữ_Liệu_Nhập_Vào'])

    if df_temp is not None:
        st.session_state.df = df_temp
        st.rerun() 

if not st.session_state.is_scanning and st.session_state.df is not None:
    st.success(f"✅ Tải dữ liệu thành công! Tổng cộng file có {len(st.session_state.df)} dòng dữ liệu.")
    
    if st.session_state.current_row > 0 and st.session_state.current_row < len(st.session_state.df):
        st.warning(f"⚠️ Phát hiện tiến trình đang quét dở ở dòng {st.session_state.current_row}. Đã khôi phục dữ liệu lỗi trước đó!")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("▶️ BẤM ĐỂ QUÉT TIẾP TỤC", type="primary", use_container_width=True):
                st.session_state.is_scanning = True
                st.rerun()
        with col_b:
            if st.button("🗑️ XÓA, QUÉT LẠI TỪ ĐẦU", use_container_width=True):
                clear_progress()
                st.session_state.current_row = 0
                st.session_state.error_results = []
                st.rerun()
    elif st.session_state.current_row == 0:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("2. 🚀 BẤM VÀO ĐÂY ĐỂ QUÉT TOÀN BỘ FILE", type="primary", use_container_width=True):
                clear_progress()
                st.session_state.is_scanning = True
                st.session_state.current_row = 0
                st.session_state.error_results = []
                st.session_state.total_links_scanned = 0
                st.rerun()
        with col2:
            if st.button("🔄 Tải file khác", use_container_width=True):
                st.session_state.df = None
                st.rerun()

if st.session_state.is_scanning:
    df = st.session_state.df
    total_rows = len(df)
    
    # Ép nhịp tim: Chạy 50 dòng một lần để trình duyệt không bị CONNECTING
    batch_size = 50 
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    current = st.session_state.current_row
    
    current_processed_show = min(current, total_rows)
    progress_show = current_processed_show / total_rows if total_rows > 0 else 1.0
    progress_bar.progress(progress_show)
    status_text.text(f"⏳ Đang quét cuốn chiếu: Xong {current_processed_show}/{total_rows} dòng... (Tự động lưu nháp)")

    if current < total_rows:
        df_batch = df.iloc[current : current + batch_size]
        url_pattern = re.compile(r'https?://[^\s,"\'<>\]}]+')
        tasks_list = []
        
        for idx, row in df_batch.iterrows():
            for col_idx, col_name in enumerate(df_batch.columns):
                val = str(row.get(col_name, ''))
                if 'http' in val or 'cdn' in val:
                    parts = val.split(',')
                    col_letter = get_excel_col_name(col_idx)
                    
                    for part in parts:
                        part = part.strip()
                        if part.startswith('https:/') and not part.startswith('https://'):
                            part = part.replace('https:/', 'https://', 1)
                        if ' ' in part:
                            part = part.replace(' ', '%20')
                            
                        matches = url_pattern.findall(part)
                        for match in matches:
                            clean_link = match.strip(".'\"\\,;>)]}")
                            if clean_link:
                                tasks_list.append((idx, col_letter, clean_link))
        
        if tasks_list:
            async def scan_batch():
                semaphore = asyncio.Semaphore(150)
                connector = aiohttp.TCPConnector(limit=200, ssl=False)
                async with aiohttp.ClientSession(connector=connector) as session:
                    tasks = [check_url(session, semaphore, item) for item in tasks_list]
                    return await asyncio.gather(*tasks)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            chunk_results = loop.run_until_complete(scan_batch())
            loop.close()
            
            valid_errors = [r for r in chunk_results if r is not None]
            st.session_state.error_results.extend(valid_errors)
            st.session_state.total_links_scanned += len(tasks_list)
        
        st.session_state.current_row += batch_size
        
        # BẢO HIỂM DỮ LIỆU: Lưu ngay kết quả xuống ổ cứng
        save_progress(st.session_state.current_row, st.session_state.error_results)
        
        gc.collect()
        st.rerun() 
        
    else:
        st.session_state.is_scanning = False 
        st.rerun()

if not st.session_state.is_scanning and st.session_state.df is not None and st.session_state.current_row >= len(st.session_state.df):
    df = st.session_state.df
    error_list = st.session_state.error_results
    
    st.success(f"🎉 HOÀN THÀNH TOÀN BỘ!")
    
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
        
        st.error(f"⚠️ Phát hiện tổng cộng {len(error_list)} link lỗi trong file.")
        st.dataframe(df_result)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False)
        
        st.download_button(
            label="3. ⬇️ TẢI FILE KẾT QUẢ VỀ MÁY",
            data=output.getvalue(),
            file_name="ket_qua_quet_FULL.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.success("🎉 Tuyệt vời! Toàn bộ link trong file của bạn đều hoạt động bình thường!")
        
    col3, col4 = st.columns(2)
    with col3:
        if st.button("🔄 Quét file mới (Xóa nháp)", type="primary"):
            clear_progress()
            st.session_state.df = None
            st.session_state.error_results = []
            st.session_state.current_row = 0
            st.rerun()
