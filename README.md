# 
# Migrasi Database
Step 1 : Copy .env.example as .env
Step 2 : Configure env
Step 3 : Create database in sql (postgres or mysql)
Step 4 : Create python .venv and install requirements.txt
Step 5 : 

## Endpoint

All routes below are mounted directly from the FastAPI app. The auth routes use the `/auth` prefix, books use `/books`, history uses `/history`, and recommendations are exposed at `/recommendations`.

### Auth

| Method | Path | Parameters | Return data |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Body: `name` (string), `email` (string, email), `password` (string, min 6 chars) | `201 Created` -> `{ access_token, token_type, user }` where `user` is `{ id, email, name }` |
| `POST` | `/auth/login` | Body: `email` (string, email), `password` (string) | `200 OK` -> `{ access_token, token_type, user }` |
| `GET` | `/auth/me` | Header: `Authorization: Bearer <token>` | `200 OK` -> `{ id, email, name }` |
| `GET` | `/auth/all` | None | `200 OK` -> array of `{ id, email, name }` |
| `GET` | `/auth/user/{user_id}` | Path: `user_id` (int) | `200 OK` -> `{ id, email, name }` |
| `POST` | `/auth/user` | Body: `name` (string), `email` (string, email), `password` (string, min 6 chars) | `201 Created` -> `{ id, email, name }` |

### Books

| Method | Path | Parameters | Return data |
| --- | --- | --- | --- |
| `GET` | `/books/genres` | None | `200 OK` -> array of genre names (`string[]`) |
| `GET` | `/books/categories` | None | `200 OK` -> array of genre names (`string[]`), alias of `/books/genres` |
| `GET` | `/books/explore` | Query: `limit` (int, default 12, max 50), `genre` (string, optional), `category` (string, optional), `search_field` (string, optional), `query` (string, optional) | `200 OK` -> array of book details |
| `GET` | `/books/most-liked` | Query: `limit` (int, default 15, max 100) | `200 OK` -> array of book details sorted by likes |
| `GET` | `/books/most-read` | Query: `limit` (int, default 15, max 100) | `200 OK` -> array of book details sorted by readers |
| `GET` | `/books/liked` | Query: `limit` (int, default 100, max 500), Header: `Authorization: Bearer <token>` | `200 OK` -> array of `{ id, created_at, book }` |
| `GET` | `/books/{book_id}` | Path: `book_id` (int) | `200 OK` -> book detail object |
| `GET` | `/books/{book_id}/recommendations` | Path: `book_id` (int), Query: `limit` (int, default 10, min 1, max 10), `threshold` (float, default 0.25, range 0-1) | `200 OK` -> array of related book details |
| `GET` | `/books/{book_id}/content` | Path: `book_id` (int) | `200 OK` -> `{ id, page_numbers }` |
| `GET` | `/books/{book_id}/content/{page_number}` | Path: `book_id` (int), `page_number` (int) | Returns the page image file (`image/jpeg` or `image/png`) |
| `POST` | `/books/{book_id}/read` | Path: `book_id` (int), Header: `Authorization: Bearer <token>` | `201 Created` -> `{ message: "Book marked as read", history_id }` |
| `POST` | `/books/` | Body: book object with `title`, `isbn`, `image_url`, `author_id`, `publisher_id`, optional `genre_ids` (int[]) | `201 Created` -> book detail object |
| `POST` | `/books/{book_id}/like` | Path: `book_id` (int), Header: `Authorization: Bearer <token>` | `200 OK` -> `{ id, total_likes }` |
| `DELETE` | `/books/{book_id}/like` | Path: `book_id` (int), Header: `Authorization: Bearer <token>` | `200 OK` -> `{ id, total_likes }` |
| `GET` | `/books/{book_id}/like` | Path: `book_id` (int), Header: `Authorization: Bearer <token>` | `200 OK` -> `{ id, is_liked }` |

### History

| Method | Path | Parameters | Return data |
| --- | --- | --- | --- |
| `GET` | `/history` | Query: `limit` (int, default 100, max 500), Header: `Authorization: Bearer <token>` | `200 OK` -> array of `{ id, read_at, book }` |
| `DELETE` | `/history/{book_id}` | Path: `book_id` (int), Header: `Authorization: Bearer <token>` | `200 OK` -> `{ message: "History deleted" }` |

### Recommendations

| Method | Path | Parameters | Return data |
| --- | --- | --- | --- |
| `GET` | `/recommendations` | Query: `limit` (int, default 10, max 100), Header: `Authorization: Bearer <token>` | `200 OK` -> array of recommended books |

### Common response shapes

`user` / `UserRead`:

```json
{
	"id": 1,
	"email": "user@example.com",
	"name": "User Name"
}
```

`auth` response:

```json
{
	"access_token": "<jwt-token>",
	"token_type": "bearer",
	"user": {
		"id": 1,
		"email": "user@example.com",
		"name": "User Name"
	}
}
```

`book detail` response:

```json
{
	"id": 1,
	"title": "Book Title",
	"author": "Author Name",
	"category": null,
	"genres": ["Fiction"],
	"publisher": "Publisher Name",
	"isbn": "9780000000000",
	"image_url": "https://example.com/image.jpg",
	"description": "Book description",
	"content_file": "content/book-1.pdf",
	"total_likes": 10,
	"total_readers": 25
}
```

`book read history` response:

```json
{
	"id": 1,
	"read_at": "2026-07-09T10:00:00Z",
	"book": {
		"id": 1,
		"title": "Book Title"
	}
}
```