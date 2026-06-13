"""Определение реального IP клиента за nginx.

nginx на эдже ставит `X-Real-IP = $remote_addr` (реальный TCP-peer соединения),
ПЕРЕЗАПИСЫВАЯ любой присланный клиентом заголовок — поэтому значение не подделать.
X-Forwarded-For формируется через `$proxy_add_x_forwarded_for`, т.е. клиентская
часть идёт первой, а наш nginx дописывает реальный IP ПОСЛЕДНИМ хопом. Значит:
доверять можно X-Real-IP или последнему элементу XFF, но НЕ первому (он клиентский).
"""
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Реальный IP клиента. Не доверяет клиентскому X-Forwarded-For[0]."""
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()[:45]
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # Последний хоп добавлен нашим nginx ($proxy_add_x_forwarded_for) → доверенный.
        last_hop = xff.split(",")[-1].strip()
        if last_hop:
            return last_hop[:45]
    if request.client:
        return request.client.host[:45]
    return "unknown"
