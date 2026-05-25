import requests
import DOMpurify

def get_book_description(book_id):
    url = f"https://www.googleapis.com/books/v1/volumes/{book_id}"
    response = requests.get(url).json()
    
    # Gunakan .get() agar tidak error jika field tidak ada
    description = response.get('volumeInfo', {}).get('description')
    return description
print (get_book_description("zyTCAlFPjgYC"))