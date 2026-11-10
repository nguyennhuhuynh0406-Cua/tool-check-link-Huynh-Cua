import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG của Huỳnh Cua")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm từ văn bản, Excel hoặc Google Sheet (Tích hợp chống tràn RAM & Auto-Retry).")

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
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    max_retries = 3 # Giải pháp 2: Thử lại tối đa 3 lần
    
    async with semaphore:
        # Giải pháp 3: Thêm độ trễ 0.1 giây trước khi gửi request để tránh nghẽn CDN
        await asyncio.sleep(0.1) 
        
        for attempt in range(max_retries):
            try:
                # Giải pháp 1: Tăng timeout lên 15 giây
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        # Nếu gặp lỗi mạng tạm thời từ máy chủ CDN (500, 502, 503, 504) hoặc bị chặn (403, 429), thử lại
                        if resp.status in [403, 429, 500, 502, 503, 504] and attempt < max_retries - 1:
                            await asyncio.sleep(1) # Nghỉ 1 giây rồi retry
                            continue
                        return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': str(resp.status)}
                    else:
                        return None # Link sống bình thường (200 OK)
                        
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Timeout (Chờ 15s không phản hồi)'}
                
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối / Link hỏng'}
                
    return None

async def process_data(df, progress_bar, status_text):
    tasks_list = []
    url_pattern = re.compile(r'(https?://[^\s,\]}\)]+)')
    
    status_text.text("🔄 Đang trích xuất link và phân loại cột, vui lòng đợi...")
    for idx, row in df.iterrows():
        for col_idx, col_name in enumerate(df.columns):
            val = str(row.get(col_name, ''))
            if 'http' in val:
                matches = url_pattern.findall(val)
                if matches:
                    col_letter = get_excel_col_name(col_idx)
                    for match in set(matches):
                        tasks_list.append((idx, col_letter, match.strip()))

    total_links = len(tasks_list)
    if total_links == 0:
        status_text.text("⚠️ Không tìm thấy đường link nào trong đoạn dữ liệu này!")
        return []

    status_text.text(f"✅ Đã phân loại xong {total_links} link. Bắt đầu quét...")
    
    # Điều chỉnh luồng cho phù hợp với việc có thêm Retry và Delay
    semaphore = asyncio.Semaphore(100) 
    connector = aiohttp.TCPConnector(limit=150, ssl=False)
    results = []
    chunk_size = 2000
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, total_links, chunk_size):
            chunk = tasks_list[i:i + chunk_size]
            tasks = [check_url(session, semaphore, item) for item in chunk]
            
            chunk_results = await asyncio.gather(*tasks)
            results.extend([r for r in chunk_results if r is not None])
            
            current_processed = min(i + chunk_size, total_links)
            progress = current_processed / total_links
            progress_bar.progress(progress)
            status_text.text(f"⏳ Đang quét an toàn: {current_processed} / {total_links} link...")
            
    status_text.text(f"🎉 Đã quét xong đoạn dữ liệu này!")
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
                csv_url = re
