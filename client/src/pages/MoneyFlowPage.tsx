import MacroFlow from '../components/MacroFlow'
import SectorAnalysis from '../components/SectorAnalysis'

// 「资金流」页 —— 三尺度资金全景(纯展示,不进策略)。
// 顶部:大盘 + 北向(P3)。下方:板块资金分析(一卡四视图:今日全景/历史热力/累计吸金/轮动RRG)。
export default function MoneyFlowPage() {
  return (
    <>
      <div className="sub" style={{ marginBottom: 14 }}>资金流全景 · A股 · 纯展示，非投资建议</div>
      <MacroFlow />
      <SectorAnalysis />
    </>
  )
}
