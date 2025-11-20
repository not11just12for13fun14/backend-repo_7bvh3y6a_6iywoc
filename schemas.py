"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user"
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    is_active: bool = Field(True, description="Whether user is active")

class Watchitem(BaseModel):
    """
    Watchlist items per user
    Collection name: "watchitem"
    """
    user_id: str = Field(..., description="User identifier")
    symbol: str = Field(..., description="Ticker symbol, e.g., AAPL")
    name: Optional[str] = Field(None, description="Company name")

class Order(BaseModel):
    """
    Paper trading orders
    Collection name: "order"
    """
    user_id: str = Field(..., description="User identifier")
    symbol: str = Field(..., description="Ticker symbol")
    side: Literal['buy','sell'] = Field(..., description="Order side")
    quantity: float = Field(..., gt=0, description="Number of shares")
    price: float = Field(..., gt=0, description="Executed price")
    status: Literal['filled','cancelled','open'] = Field('filled', description="Order status")
