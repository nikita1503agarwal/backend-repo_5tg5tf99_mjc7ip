import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, BlogPost, ContactMessage

app = FastAPI(title="SaaS Landing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "SaaS Landing API running"}

# Utility to convert Mongo docs

def serialize_doc(doc: dict):
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert datetime to isoformat
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d

# Auth (very simple demo: signup/signin storing hashed passwords; in real prod use proper auth)

class SignUpPayload(BaseModel):
    name: str
    email: EmailStr
    password_hash: str
    salt: str

class SignInPayload(BaseModel):
    email: EmailStr
    password_hash: str

@app.post("/auth/signup")
def signup(payload: SignUpPayload):
    # check if user exists
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(name=payload.name, email=payload.email, password_hash=payload.password_hash, salt=payload.salt)
    user_id = create_document("user", user)
    return {"id": user_id, "email": payload.email, "name": payload.name}

@app.post("/auth/signin")
def signin(payload: SignInPayload):
    existing = db["user"].find_one({"email": payload.email})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    if existing.get("password_hash") != payload.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"id": str(existing["_id"]), "email": existing["email"], "name": existing.get("name")}

# Blog

@app.get("/blog", response_model=List[dict])
def list_posts():
    posts = get_documents("blogpost", {"published": True})
    posts.sort(key=lambda x: x.get("published_at") or x.get("created_at"), reverse=True)
    return [serialize_doc(p) for p in posts]

@app.get("/blog/{slug}")
def get_post(slug: str):
    post = db["blogpost"].find_one({"slug": slug})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return serialize_doc(post)

class CreatePostPayload(BaseModel):
    title: str
    slug: str
    excerpt: Optional[str] = None
    content: str
    author: str
    tags: Optional[List[str]] = None
    published: bool = True

@app.post("/blog")
def create_post(payload: CreatePostPayload):
    if db["blogpost"].find_one({"slug": payload.slug}):
        raise HTTPException(status_code=400, detail="Slug already exists")
    post = BlogPost(
        title=payload.title,
        slug=payload.slug,
        excerpt=payload.excerpt,
        content=payload.content,
        author=payload.author,
        tags=payload.tags or [],
        published=payload.published,
        published_at=datetime.utcnow() if payload.published else None,
    )
    post_id = create_document("blogpost", post)
    return {"id": post_id, "slug": payload.slug}

# Contact form

class ContactPayload(BaseModel):
    name: str
    email: EmailStr
    message: str
    subject: Optional[str] = None

@app.post("/contact")
def submit_contact(payload: ContactPayload):
    msg = ContactMessage(name=payload.name, email=payload.email, message=payload.message, subject=payload.subject)
    msg_id = create_document("contactmessage", msg)
    return {"id": msg_id, "status": "received"}

# Health check for DB

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
