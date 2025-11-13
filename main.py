from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import RedirectResponse, HTMLResponse
import sqlite3
from contextlib import contextmanager

app = FastAPI()

# Database setup
DATABASE = "urls.db"


def init_db():
    """Initialize the database with the urls table"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            code TEXT PRIMARY KEY,
            url TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE)
    try:
        yield conn
    finally:
        conn.close()


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()


# Pydantic model for creating URL entries
class URLCreate(BaseModel):
    code: str
    url: str


@app.get("/")
async def read_root():
    return {"message": "Welcome to the FastAPI application!"}


@app.get("/manage", response_class=HTMLResponse)
async def manage_page():
    """Display management page for creating and editing entries"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code, url FROM urls ORDER BY code")
        entries = cursor.fetchall()

    entries_html = ""
    for code, url in entries:
        entries_html += f"""
        <tr>
            <td><input type="text" value="{code}" readonly style="border:none; background:transparent;"></td>
            <td><input type="text" id="url-{code}" value="{url}" style="width:400px;"></td>
            <td>
                <button onclick="updateEntry('{code}')">Update</button>
                <button onclick="deleteEntry('{code}')">Delete</button>
            </td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>URL Shortener - Manage</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
            h1 {{ color: #333; }}
            .form-group {{ margin: 15px 0; }}
            label {{ display: inline-block; width: 80px; font-weight: bold; }}
            input {{ padding: 8px; margin: 5px; }}
            button {{ padding: 8px 15px; background: #007bff; color: white; border: none; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #f4f4f4; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
        </style>
    </head>
    <body>
        <h1>URL Shortener Management</h1>
        
        <h2>Create New Entry</h2>
        <form id="createForm">
            <div class="form-group">
                <label>Code:</label>
                <input type="text" id="code" required>
            </div>
            <div class="form-group">
                <label>URL:</label>
                <input type="url" id="url" required style="width:400px;">
            </div>
            <button type="submit">Create</button>
        </form>
        <div id="message"></div>
        
        <h2>Existing Entries</h2>
        <table>
            <tr>
                <th>Code</th>
                <th>URL</th>
                <th>Actions</th>
            </tr>
            {entries_html}
        </table>
        
        <script>
            document.getElementById('createForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const code = document.getElementById('code').value;
                const url = document.getElementById('url').value;
                
                const response = await fetch('/shorten', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ code, url }})
                }});
                
                const data = await response.json();
                const messageDiv = document.getElementById('message');
                
                if (response.ok) {{
                    messageDiv.innerHTML = '<p class="success">Entry created successfully!</p>';
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    messageDiv.innerHTML = `<p class="error">${{data.detail}}</p>`;
                }}
            }});
            
            async function updateEntry(code) {{
                const url = document.getElementById(`url-${{code}}`).value;
                
                const response = await fetch(`/update/${{code}}`, {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ url }})
                }});
                
                if (response.ok) {{
                    alert('Entry updated successfully!');
                }} else {{
                    alert('Failed to update entry');
                }}
            }}
            
            async function deleteEntry(code) {{
                if (!confirm(`Delete entry for code: ${{code}}?`)) return;
                
                const response = await fetch(`/delete/${{code}}`, {{
                    method: 'DELETE'
                }});
                
                if (response.ok) {{
                    location.reload();
                }} else {{
                    alert('Failed to delete entry');
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/shorten")
async def create_short_url(url_data: URLCreate):
    """Create a new short URL entry"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO urls (code, url) VALUES (?, ?)",
                (url_data.code, url_data.url),
            )
            conn.commit()
            return {
                "code": url_data.code,
                "url": url_data.url,
                "message": "Short URL created successfully",
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Code already exists")


@app.put("/update/{code}")
async def update_url(code: str, url_data: dict):
    """Update an existing URL entry"""
    try:
        new_url = url_data["url"]
    except KeyError:
        raise HTTPException(status_code=500, detail="Missing 'url' field in request body")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE urls SET url = ? WHERE code = ?", (new_url, code)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Code not found")
        return {"message": "URL updated successfully"}


@app.delete("/delete/{code}")
async def delete_url(code: str):
    """Delete a URL entry"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM urls WHERE code = ?", (code,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Code not found")
        return {"message": "Entry deleted successfully"}


@app.get("/{code}")
async def resolve(code: str):
    """Resolve a short code to its URL and redirect"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM urls WHERE code = ?", (code,))
        result = cursor.fetchone()

        if result:
            return RedirectResponse(result[0], status_code=302)

        # Redirect to management page if code not found
        return RedirectResponse("/manage", status_code=302)
