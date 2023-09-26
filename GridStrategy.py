import backtrader as bt
import pandas as pd
import matplotlib.pyplot as plt

# load 1m candles with Pythia signals from csv
# df = pd.read_csv('./data/15m-signals-60d.csv')
df = pd.read_csv('./data/15m-signals-365d.csv')
# df = pd.read_csv('./data/1m_01.07.2023-today.csv')
# df = pd.read_csv('./data/1m_27.03.2023-today.csv')

# Leave only the necessary columns
df = df[['timestamp', 'open', 'high', 'low', 'close', 'signal', 'volume']]

# Convert timestamp from ms to normal timestamp
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# Assign timestamp as an index
df.set_index('timestamp', inplace=True)

class SignalData(bt.feeds.PandasData):
    lines = ('signal',)
    params = (('signal', -1),)

class GridStrategy(bt.Strategy):
    #APY 21.81%
    # params = ( 
    #     ('safe_order_step', 0.007),
    #     ('bet_percent', 0.04),
    #     ('num_orders', 8),
    #     ('martingale_factor', 1.24),
    #     ('safe_order_step_factor', 1.07),
    #     ('take_profit', 0.003),
    #     ('overbought', 80),
    #     ('debug', False)
    # )

    #APY 24.22%
    params = ( 
        ('safe_order_step', 0.007),
        ('bet_percent', 0.04),
        ('num_orders', 8),
        ('martingale_factor', 1.24),
        ('safe_order_step_factor', 1.05),
        ('take_profit', 0.003),
        ('overbought', 80),
        ('debug', False)
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        if self.params.debug:
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.data_signal = self.datas[0].signal
        self.orders = []  # List to hold our safe orders

        self.bar_counter = 0
        self.max_duration = []
        self.grid_execurions = []

        self.stoch = bt.indicators.StochasticFast(self.data, safediv=True)

    def notify_order(self, order):

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order in self.orders:
                self.log(f'GRID EXECUTED, {order.executed.price}, price: {self.position.price}, , size: {self.position.size}')
                self.grid_execurions[-1] += 1

        elif order.status in [order.Margin, order.Rejected]:
            self.log(f'Order status:, {order.status}')

    def cancel_all_orders(self):
        self.log('All Orders Canceled')
        for order in self.orders:
            self.cancel(order)
            order = None
        self.orders = []
        self.take_profit = None

    def place_new_grid(self, price, size):
        for i in range(self.params.num_orders):
            order = self.buy(exectype=bt.Order.Limit,
                             size=size * self.params.martingale_factor ** i,
                             price=price * (1 - (self.params.safe_order_step * (self.params.safe_order_step_factor ** i) * (i+1))))
            self.orders.append(order)
        self.grid_execurions.append(0)

    def next(self):

        if self.getposition():
            self.bar_counter += 1

        if not self.getposition():
            if self.data_signal[0] == 1:
                size = self.params.bet_percent * self.broker.getvalue() / self.data.close[0]
                self.log(f'signal:,{self.data_signal[0], self.position.size}')
                self.buy(exectype=bt.Order.Market, size=size)
                self.place_new_grid(self.data.close[0], size)
        # elif self.getposition() and self.data.close[0] >= self.position.price * (1 + self.params.take_profit):
        elif self.getposition() and self.data.close[0] >= self.position.price * (1 + self.params.take_profit) and self.stoch.percK < self.stoch.percD and self.stoch.percK[0] > self.params.overbought:
            self.log(f'TP EXECUTED, {self.position.price}, position: {self.position.size}')
            self.close()
            self.cancel_all_orders()
            self.max_duration.append(self.bar_counter)
            self.bar_counter = 0


# Create an instance of Cerebro
cerebro = bt.Cerebro()

# Set the broker's commission
cerebro.broker.setcommission(commission=0.0004, margin=True)

# Set up the initial capital
cerebro.broker.setcash(3000)

# Add an analyzer to calculate the APR
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
cerebro.addanalyzer(bt.analyzers.TimeReturn,
                    _name='time_return', timeframe=bt.TimeFrame.Years)
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

# Upload the data to backtrader
data = SignalData(dataname=df, open='open', high='high', low='low', close='close',
                  volume='volume', openinterest=None, timeframe=bt.TimeFrame.Minutes, compression=15)
cerebro.adddata(data)

# Add a strategy
cerebro.addstrategy(GridStrategy)

# Start backtesting
results = cerebro.run()

# Deal Analyzer
trade_analysis = results[0].analyzers.tradeanalyzer.get_analysis()
sharpe_ratio = results[0].analyzers.sharpe.get_analysis()
sqn_value = results[0].analyzers.sqn.get_analysis()['sqn']
drawdown = results[0].analyzers.drawdown.get_analysis()
max_drawdown = drawdown['max']['drawdown']

total_trades = trade_analysis.total.closed
profit_trades = trade_analysis.won.total
loss_trades = trade_analysis.lost.total
win_rate = (profit_trades / total_trades) * 100 if total_trades != 0 else 0

# Output APR
total_return = results[0].analyzers.getbyname('returns').get_analysis()['rtot']

start_date = df.index[0]  # Start date of the test period
end_date = df.index[-1]  # End date of the testing period

period = (end_date - start_date).days / 365

apr = (1 + total_return) ** (1 / period) - 1  # Calculate APR for the year
apr_period = apr * period  # Calculate the APR for the test period


print('Executed grids:', results[0].grid_execurions)
print('Duretion od deals:', results[0].max_duration)

print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
print('--- Metrics ---')
print('Total trades:', total_trades)
print('Profit trades:', profit_trades)
print('Loss trades:', loss_trades)
print('Win Rate [%]:', win_rate)
print('Max deal duration [days]:', max(results[0].max_duration)/60/24)
print('Max Drawdown [%]:', max_drawdown)
print('Average deals duration:', sum(
    results[0].max_duration)/60/24 / total_trades)
print(f'Sharpe Ratio: {sharpe_ratio["sharperatio"]}')
print(f'SQN: {sqn_value}')
print('--- Grid stats ---')
print('Average executed SO:', sum(results[0].grid_execurions) / total_trades)
print('Max executed SO:', max(results[0].grid_execurions))
print('--- APR ---')
print('APR for the testing period: {:.2%}'.format(apr_period))
print('APR for the year: {:.2%}'.format(apr))


# Output the graph
cerebro.plot(style='candlestick', volume=False)
