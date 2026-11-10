import streamlit as st
import pandas as pd
import asyncio
import aiohttp
import re
import io
import gc

st.set_page_config(page_title="Tool Check Đa Năng", layout="wide")
st.title("🛠️ CÔNG CỤ KIỂM TRA LINK ĐA NĂNG của Huỳnh Cua")
st.markdown("Hỗ trợ quét URL trực tiếp, link ảnh, link sản phẩm từ văn bản, Excel hoặc Google Sheet. **(Phiên bản: Bóc tách link dính chùm & Auto toàn file)**")

def get_excel_col_name(n):
    result = ""
    n += 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

async def check_url(session, semaphore, item):
    idx, col_letter, url = item
    
    # Bổ sung Headers chuyên biệt để vượt CDN của TGDĐ/ĐMX
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
        await asyncio.sleep(0.1) 
        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        if resp.status in [403, 429, 500, 502, 503, 504] and attempt < max_retries - 1:
                            await asyncio.sleep(1.5)
                            continue
                        return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': str(resp.status)}
                    else:
                        return None
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Timeout (Chờ 15s)'}
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5)
                    continue
                return {'idx': idx, 'col_letter': col_letter, 'Link_lỗi': url, 'Mã_Lỗi': 'Lỗi kết nối / Link hỏng'}
    return None

async def process_data(df, progress_bar, status_text):
    tasks_list = []
    
    # Regex CỰC MẠNH: Bắt đầu bằng http/https, và lấy mọi ký tự cho đến khi đụng dấu phẩy, khoảng trắng, hoặc ngoặc
    url_pattern = re.compile(r'https?://[^\s,"\'<>\]}]+')
    
    status_text.text("🔄 Đang bóc tách từng link dính chùm trong ô, vui lòng đợi...")
    for idx, row in df.iterrows():
        for col_idx, col_name in enumerate(df.columns):
            val = str(row.get(col_name, ''))
            if 'http' in val:
                # Tự động dò và tách rời các link dù chúng dính liền bằng dấu phẩy
                matches = url_pattern.findall(val)
                if matches:
                    col_letter = get_excel_col_name(col_idx)
                    for match in set(matches):
                        # Quét dọn lần cuối để chắc chắn không còn dấu rác nào
                        clean_link = match.strip(".'\"\\,;>)]}")
                        if clean_link:
                            tasks_list.append((idx, col_letter, clean_link))

    total_links = len(tasks_list)
    if total_links == 0:
        status_text.text("⚠️ Không tìm thấy đường link nào trong dữ liệu!")
        return []

    status_text.text(f"✅ Đã bóc tách thành công {total_links} link riêng biệt. Bắt đầu quét...")
    
    semaphore = asyncio.Semaphore(150) 
    connector = aiohttp.TCPConnector(limit=200, ssl=False)
    results = []
    chunk_size = 1500 
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, total_links, chunk_size):
            chunk = tasks_list[i:i + chunk_size]
            tasks = [check_url(session, semaphore, item) for item in chunk]
            
            chunk_results = await asyncio.gather(*tasks)
            results.extend([r for r in chunk_results if r is not None])
            
            current_processed = min(i + chunk_size, total_links)
            progress = current_processed / total_links
            progress_bar.progress(progress)
            status_text.text(f"⏳ Hệ thống đang quét tự động: {current_processed} / {total_links} link. (VUI LÒNG KHÔNG TẮT TAB NÀY)")
            
            del tasks
            del chunk_results
            gc.collect() 
            
    status_text.text(f"🎉 Đã quét thành công toàn bộ {total_links} link!")
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
    
    st.warning("⚠️ LƯU Ý: Với file cực lớn (trên 10.000 dòng), quá trình quét sẽ mất khoảng 5 - 15 phút. Bạn hãy bấm quét 1 lần và **MỞ TREO TAB NÀY**, đừng tải lại trang nhé!")
    
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
