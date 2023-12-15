from app.services.trading_service import get_balance
from dotenv import load_dotenv


def test_get_balance():
    load_dotenv()
    data = get_balance()
    assert 'total' in data
    assert data['total'] >= 0
    assert 'exchanges' in data
    assert 'BINANCE' in data['exchanges']
    assert 'USDT' in data['exchanges']['BINANCE']
    assert data['exchanges']['BINANCE']['USDT'] >= 0
    assert data['exchanges']['BINANCE']['total'] >= 0
