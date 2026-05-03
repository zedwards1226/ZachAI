import { useEffect, useRef } from 'react'

/**
 * Embeds a TradingView Advanced Chart for the given symbol.
 * Free, real-time, no API key. Supports overlay annotations + indicators.
 *
 * symbol: 'BINANCE:BTCUSDT' | 'BINANCE:ETHUSDT' | etc.
 *         Free real-time crypto data via Binance feed inside the widget.
 */
export default function LiveChart({
  symbol = 'BINANCE:BTCUSDT',
  interval = '1',         // 1m candles
  height = 360,
  containerId,
  studies = [],
}) {
  const ref = useRef(null)
  const id = containerId || `tv-${symbol.replace(/[^a-z0-9]/gi, '_')}`

  useEffect(() => {
    if (!ref.current) return
    // Clear any prior content (re-renders)
    ref.current.innerHTML = ''
    // TradingView's loader script per their docs
    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.type = 'text/javascript'
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: 'America/New_York',
      theme: 'dark',
      style: '1',                  // candlesticks
      locale: 'en',
      enable_publishing: false,
      hide_top_toolbar: false,
      hide_side_toolbar: true,
      allow_symbol_change: false,
      withdateranges: false,
      hide_volume: false,
      backgroundColor: 'rgba(15, 15, 20, 1)',
      gridColor: 'rgba(42, 42, 58, 0.4)',
      studies,
      support_host: 'https://www.tradingview.com',
    })
    ref.current.appendChild(script)
  }, [symbol, interval, JSON.stringify(studies)])

  return (
    <div className="rounded-xl overflow-hidden border" style={{ borderColor: '#2a2a3a', background: '#0f0f14' }}>
      <div ref={ref} id={id} style={{ height, width: '100%' }} />
    </div>
  )
}
