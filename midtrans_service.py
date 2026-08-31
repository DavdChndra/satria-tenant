import midtransclient
import hashlib
import os


def get_snap_client():
    """
    Buat client Snap Midtrans dari environment variable.
    Set MIDTRANS_SERVER_KEY, MIDTRANS_CLIENT_KEY, MIDTRANS_IS_PRODUCTION
    di file .env (lihat .env.example).
    """
    return midtransclient.Snap(
        is_production=os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true",
        server_key=os.environ.get("MIDTRANS_SERVER_KEY", ""),
        client_key=os.environ.get("MIDTRANS_CLIENT_KEY", ""),
    )


def create_transaction(order_id: str, gross_amount: int, customer: dict, item_name: str):
    """
    Membuat transaksi Snap dan mengembalikan dict berisi 'token' dan 'redirect_url'.
    customer: {"first_name": ..., "email": ..., "phone": ...}
    """
    snap = get_snap_client()
    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": gross_amount,
        },
        "item_details": [
            {
                "id": "booth-registration",
                "price": gross_amount,
                "quantity": 1,
                "name": item_name[:50],  # Midtrans membatasi panjang nama item
            }
        ],
        "customer_details": {
            "first_name": customer.get("first_name", ""),
            "email": customer.get("email", ""),
            "phone": customer.get("phone", ""),
        },
        "credit_card": {"secure": True},
    }
    return snap.create_transaction(param)


def verify_notification_signature(order_id: str, status_code: str, gross_amount: str, signature_key: str) -> bool:
    """
    Verifikasi signature_key dari webhook notification Midtrans.
    Formula resmi: SHA512(order_id + status_code + gross_amount + server_key)
    """
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    computed = hashlib.sha512(raw.encode("utf-8")).hexdigest()
    return computed == signature_key


def map_transaction_status(transaction_status: str, fraud_status: str = None) -> str:
    """Memetakan status transaksi Midtrans ke status internal aplikasi."""
    if transaction_status == "capture":
        if fraud_status == "accept":
            return "paid"
        elif fraud_status == "challenge":
            return "pending"
        return "pending"
    elif transaction_status == "settlement":
        return "paid"
    elif transaction_status in ("cancel", "deny"):
        return "cancelled"
    elif transaction_status == "expire":
        return "expired"
    elif transaction_status == "failure":
        return "failed"
    elif transaction_status == "refund" or transaction_status == "partial_refund":
        return "refunded"
    return "pending"
