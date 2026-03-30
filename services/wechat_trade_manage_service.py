"""
微信小程序「发货信息管理服务」相关事件处理。

官方说明：trade_manage_* 等事件由微信推送到小程序配置的「服务器地址(URL)」，
与微信支付 V3 的支付结果通知 URL 可能不是同一个入口；此处逻辑可被多处复用。
"""
from __future__ import annotations

from typing import Any, Dict

from core.database import get_conn
from core.logging import get_logger

logger = get_logger(__name__)


def process_trade_manage_remind_shipping(data: Dict[str, Any]) -> None:
    transaction_id = data.get("transaction_id")
    merchant_trade_no = data.get("merchant_trade_no")
    logger.warning(
        "微信提醒发货 trade_manage_remind_shipping: transaction_id=%s merchant_trade_no=%s",
        transaction_id,
        merchant_trade_no,
    )


def process_trade_manage_order_settlement(data: Dict[str, Any]) -> None:
    """
    trade_manage_order_settlement 在「发货时」与「结算时」都会推送。
    仅当带有结算侧字段（settlement_time / confirm_receive_time）时，才将本地订单标为已完成，
    避免发货推送误把订单直接变成 completed。
    """
    transaction_id = data.get("transaction_id")
    merchant_trade_no = data.get("merchant_trade_no")
    settlement_time = data.get("settlement_time")
    confirm_receive_time = data.get("confirm_receive_time")

    if not transaction_id:
        logger.warning(
            "trade_manage_order_settlement 缺少 transaction_id: merchant_trade_no=%s keys=%s",
            merchant_trade_no,
            list(data.keys()),
        )
        return

    if not settlement_time and not confirm_receive_time:
        logger.info(
            "trade_manage_order_settlement 发货阶段或非结算推送，跳过本地完成: transaction_id=%s",
            transaction_id,
        )
        return

    logger.info(
        "订单结算/确认收货推送: transaction_id=%s merchant_trade_no=%s settlement_time=%s confirm_receive_time=%s",
        transaction_id,
        merchant_trade_no,
        settlement_time,
        confirm_receive_time,
    )

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, order_number, status FROM orders WHERE transaction_id=%s",
                    (transaction_id,),
                )
                order = cur.fetchone()
                if order and order["status"] != "completed":
                    cur.execute(
                        "UPDATE orders SET status='completed', completed_at=NOW() WHERE id=%s",
                        (order["id"],),
                    )
                    conn.commit()
                    logger.info("订单 %s 已根据微信结算/确认收货事件更新为已完成", order["order_number"])
    except Exception as e:
        logger.error("处理 trade_manage_order_settlement 失败: %s", e, exc_info=True)


def process_trade_manage_remind_access_api(data: Dict[str, Any]) -> None:
    logger.info(
        "trade_manage_remind_access_api: msg=%s keys=%s",
        data.get("msg"),
        list(data.keys()),
    )


def process_wxa_trade_controlled(data: Dict[str, Any]) -> None:
    logger.warning(
        "wxa_trade_controlled 小程序需接入订单发货管理: msg=%s keys=%s",
        data.get("msg"),
        list(data.keys()),
    )
