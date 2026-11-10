import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm từ văn bản, Excel hoặc Google Sheet (Tốc độ an toàn).")

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
    async with semaphore:
        try:
            # Thời gian chờ an toàn: 8 giây
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), headers=headers, allow_redirects=True) as resp:
                if resp.status >= 400:
                    return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': str(resp.status)}
        except asyncio.TimeoutError:
            return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Timeout'}
        except Exception:
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
        status_text.text("⚠️ Không tìm thấy đường link nào trong dữ liệu!")
        return []

    status_text.text(f"✅ Đã phân loại xong {total_links} link. Bắt đầu quét...")
    
    # TỐC ĐỘ CÂN BẰNG - AN TOÀN
    semaphore = asyncio.Semaphore(100) # Quét 100 link cùng lúc
    connector = aiohttp.TCPConnector(limit=150, ssl=False)
    results = []
    chunk_size = 2000 # Nghỉ nhịp sau mỗi 2000 link
    
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
            
    status_text.text(f"🎉 Đã quét xong toàn bộ {total_links} link!")
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
    if st.button("2. BẤM VÀO ĐÂY ĐỂ QUÉT LINK", type="primary"):
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
            
            st.error(f"⚠️ Phát hiện {len(error_list)} link lỗi!")
            st.dataframe(df_result)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_result.to_excel(writer, index=False)
            
            st.download_button(
                label="3. ⬇️ TẢI FILE KẾT QUẢ VỀ MÁY",
                data=output.getvalue(),
                file_name="ket_qua_loi_theo_cot.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.success("🎉 Tất cả link đều hoạt động bình thường!")
