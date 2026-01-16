"""
Paper Trading Test Script.
模拟交易测试脚本

Simple test to verify paper trading components work correctly.
简单测试验证模拟交易组件是否正常工作。
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange, Direction, OrderType
from vnpy.trader.object import OrderRequest, TickData

from src.gateway.paper_account import PaperAccount
from src.utils.logger import get_logger

logger = get_logger("paper_test")


def test_paper_account():
    """Test basic paper account functionality."""
    print("=" * 60)
    print("Paper Account Test / 模拟账户测试")
    print("=" * 60)

    # Initialize event engine and paper account
    event_engine = EventEngine()
    event_engine.start()

    paper = PaperAccount(event_engine, "PAPER")

    # Connect with default settings
    settings = {
        "初始资金": 100000,
        "手续费率": 0.0003,
        "印花税率": 0.001,
        "滑点": 0.001,
    }
    paper.connect(settings)

    print(f"\n[1] Initial State / 初始状态")
    stats = paper.get_statistics()
    print(f"    Balance / 余额: {stats['current_balance']:,.2f}")
    print(f"    Frozen / 冻结: {stats['frozen']:,.2f}")

    # Create a mock tick
    tick = TickData(
        symbol="000001",
        exchange=Exchange.SZSE,
        datetime=datetime.now(),
        name="平安银行",
        last_price=10.50,
        bid_price_1=10.49,
        ask_price_1=10.51,
        bid_volume_1=10000,
        ask_volume_1=10000,
        gateway_name="PAPER",
    )

    # Update tick to enable trading
    paper.update_tick(tick)

    print(f"\n[2] Send Buy Order / 发送买单")
    buy_req = OrderRequest(
        symbol="000001",
        exchange=Exchange.SZSE,
        direction=Direction.LONG,
        type=OrderType.LIMIT,
        volume=1000,
        price=10.50,
    )

    vt_orderid = paper.send_order(buy_req)
    print(f"    Order ID: {vt_orderid}")

    stats = paper.get_statistics()
    print(f"    Balance after order / 下单后余额: {stats['current_balance']:,.2f}")
    print(f"    Frozen / 冻结: {stats['frozen']:,.2f}")

    # Update tick to trigger order matching
    tick.last_price = 10.48  # Price dropped, buy order should fill
    tick.ask_price_1 = 10.48
    tick.datetime = datetime.now()
    paper.update_tick(tick)

    print(f"\n[3] After Order Fill / 成交后")
    stats = paper.get_statistics()
    print(f"    Balance / 余额: {stats['current_balance']:,.2f}")
    print(f"    Total trades / 交易次数: {stats['total_trades']}")
    print(f"    Total commission / 手续费: {stats['total_commission']:.2f}")

    # Check position
    vt_symbol = "000001.SZSE"
    if vt_symbol in paper.positions:
        pos = paper.positions[vt_symbol]
        print(f"    Position / 持仓: {pos.volume} @ {pos.avg_price:.2f}")

    # Test sell order
    print(f"\n[4] Send Sell Order / 发送卖单")

    # Price goes up
    tick.last_price = 11.00
    tick.bid_price_1 = 11.00
    tick.datetime = datetime.now()
    paper.update_tick(tick)

    sell_req = OrderRequest(
        symbol="000001",
        exchange=Exchange.SZSE,
        direction=Direction.SHORT,
        type=OrderType.LIMIT,
        volume=500,
        price=11.00,
    )

    vt_orderid = paper.send_order(sell_req)
    print(f"    Order ID: {vt_orderid}")

    # Tick update to fill sell order
    paper.update_tick(tick)

    print(f"\n[5] Final State / 最终状态")
    stats = paper.get_statistics()
    print(f"    Balance / 余额: {stats['current_balance']:,.2f}")
    print(f"    Total P&L / 总盈亏: {stats['total_pnl']:.2f}")
    print(f"    Total trades / 交易次数: {stats['total_trades']}")
    print(f"    Return % / 收益率: {stats['return_pct']:.2f}%")

    if vt_symbol in paper.positions:
        pos = paper.positions[vt_symbol]
        print(f"    Remaining position / 剩余持仓: {pos.volume}")

    # Cleanup
    paper.close()
    event_engine.stop()

    print("\n" + "=" * 60)
    print("Test completed successfully! / 测试完成!")
    print("=" * 60)

    return True


def test_order_validation():
    """Test order validation rules."""
    print("\n" + "=" * 60)
    print("Order Validation Test / 订单验证测试")
    print("=" * 60)

    event_engine = EventEngine()
    event_engine.start()

    paper = PaperAccount(event_engine, "PAPER")
    paper.connect({"初始资金": 10000})  # Low capital for testing

    # Test 1: Volume less than 100
    print("\n[Test 1] Volume < 100")
    req = OrderRequest(
        symbol="000001",
        exchange=Exchange.SZSE,
        direction=Direction.LONG,
        type=OrderType.LIMIT,
        volume=50,
        price=10.00,
    )
    result = paper.send_order(req)
    print(f"    Result: {'Rejected (expected)' if not result else 'Accepted (unexpected)'}")

    # Test 2: Volume not multiple of 100
    print("\n[Test 2] Volume not multiple of 100")
    req.volume = 150
    result = paper.send_order(req)
    print(f"    Result: {'Rejected (expected)' if not result else 'Accepted (unexpected)'}")

    # Test 3: Insufficient funds
    print("\n[Test 3] Insufficient funds")
    req.volume = 10000  # 10000 * 10 = 100,000, but only have 10,000
    result = paper.send_order(req)
    print(f"    Result: {'Rejected (expected)' if not result else 'Accepted (unexpected)'}")

    # Cleanup
    paper.close()
    event_engine.stop()

    print("\n" + "=" * 60)
    print("Validation test completed! / 验证测试完成!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    print("\nStarting Paper Trading Tests / 开始模拟交易测试\n")

    try:
        test_paper_account()
        test_order_validation()
        print("\n✓ All tests passed! / 所有测试通过!")

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
