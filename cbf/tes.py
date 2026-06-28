import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

def scrape_web_gramedia(keywords_array):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    semua_buku = []
    
    for kw in keywords_array:
        print(f"\n🔎 Mencari di Web Gramedia untuk keyword: {kw.upper()}")
        
        # Mengakses langsung halaman pencarian web Gramedia
        url = f"https://www.gramedia.com/search?submit=Search&search={kw}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"❌ Gagal memuat halaman web untuk keyword '{kw}'")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Mencari elemen kartu produk (class ini bisa berubah tergantung update web Gramedia)
            # Anda perlu inspect element di browser untuk memastikan class terbarunya jika tidak muncul
            items = soup.find_all('div', class_='per-card-product') 
            
            if not items:
                print(f"⚠️ Tidak ada elemen buku yang ditemukan untuk keyword '{kw}' (atau struktur web berubah).")
                continue
                
            for index, item in enumerate(items[:5], 1): # Ambil 5 teratas
                try:
                    judul_elem = item.find('p', class_='title-card-product')
                    judul = judul_elem.text.strip() if judul_elem else 'N/A'
                    
                    penulis_elem = item.find('span', class_='author-card-product')
                    penulis = penulis_elem.text.strip() if penulis_elem else 'Anonim'
                    
                    harga_elem = item.find('p', class_='price-card-product')
                    harga = harga_elem.text.strip() if harga_elem else 'N/A'
                    
                    # Pada halaman pencarian, deskripsi biasanya tidak muncul lengkap.
                    # Kita buat placeholder, atau ambil link-nya untuk di-scrape kemudian.
                    deskripsi = "Buka halaman detail untuk sinopsis lengkap."
                    
                    print(f"   [{index}] Didapat: {judul[:30]}...")
                    
                    semua_buku.append({
                        'Keyword': kw,
                        'Judul': judul,
                        'Penulis': penulis,
                        'Harga': harga,
                        'Deskripsi': deskripsi
                    })
                except Exception as e:
                    continue
                    
            time.sleep(2) # Jeda aman
            
        except Exception as e:
            print(f"❌ Error saat memproses '{kw}': {e}")
            
    if semua_buku:
        df = pd.DataFrame(semua_buku)
        df.to_excel("dataset_web_gramedia.xlsx", index=False)
        print(f"\n✅ Berhasil! {len(semua_buku)} data disimpan di 'dataset_web_gramedia.xlsx'")
    else:
        print("\n❌ Tetap tidak ada data yang bisa diambil. Periksa koneksi internet Anda.")

# Coba jalankan ulang
scrape_web_gramedia(["novel", "sejarah"])