from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime


class StoreInfoCreateReq(BaseModel):
    """创建店铺信息请求"""
    user_id: int = Field(..., description="用户ID")
    store_name: str = Field(..., min_length=2, max_length=100, description="店铺名称")
    store_logo_image_id: Optional[str] = Field(None, description="店铺LOGO图片ID")
    store_description: Optional[str] = Field(None, max_length=500, description="店铺简介")
    contact_name: str = Field(..., max_length=20, description="联系人姓名")
    contact_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="联系人手机号")
    contact_email: Optional[str] = Field(None, max_length=100, description="联系人邮箱")
    business_hours: Optional[str] = Field(None, max_length=100, description="营业时间")
    store_address: Optional[str] = Field(None, max_length=200, description="店铺地址")


class StoreInfoUpdateReq(BaseModel):
    """更新店铺信息请求"""
    store_name: Optional[str] = Field(None, min_length=2, max_length=100, description="店铺名称")
    store_logo_image_id: Optional[str] = Field(None, description="店铺LOGO图片ID")
    store_description: Optional[str] = Field(None, max_length=500, description="店铺简介")
    contact_name: Optional[str] = Field(None, max_length=20, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$", description="联系人手机号")
    contact_email: Optional[str] = Field(None, max_length=100, description="联系人邮箱")
    business_hours: Optional[str] = Field(None, max_length=100, description="营业时间")
    store_address: Optional[str] = Field(None, max_length=200, description="店铺地址")


class StoreInfoResp(BaseModel):
    """店铺信息响应"""
    store_id: int
    user_id: int
    store_name: str
    store_logo_image_id: Optional[str] = None
    store_logo_url: Optional[str] = None
    store_description: Optional[str] = None
    contact_name: str
    contact_phone: str
    contact_email: Optional[str] = None
    business_hours: Optional[str] = None
    store_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StoreSetupStatusResp(BaseModel):
    """店铺设置状态响应"""
    user_id: int
    has_store_permission: bool = False
    has_payment_account: bool = False  # 支付进件是否成功
    has_store_info: bool = False  # 是否已设置店铺信息
    can_setup_store: bool = False  # 是否可以设置店铺（需has_store_permission=True）
    store_info: Optional[StoreInfoResp] = None


class StoreLogoUploadResp(BaseModel):
    """LOGO上传响应"""
    image_id: str
    image_url: str
    file_size: int