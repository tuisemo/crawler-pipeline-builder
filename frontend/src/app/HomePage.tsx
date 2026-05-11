import { Button } from 'antd'
import { useNavigate } from 'react-router-dom'

interface FeatureCardProps {
  tag: string
  title: string
  description: string
}

function FeatureCard({ tag, title, description }: FeatureCardProps) {
  return (
    <div className="home-feature-card">
      <span className="home-feature-tag">{tag}</span>
      <h3 className="home-feature-title">{title}</h3>
      <p className="home-feature-desc">{description}</p>
    </div>
  )
}

interface WorkflowStepProps {
  label: string
  index: number
}

function WorkflowStep({ label, index }: WorkflowStepProps) {
  return (
    <div className="home-workflow-step">
      <span className="home-workflow-index">{String(index).padStart(2, '0')}</span>
      <span className="home-workflow-label">{label}</span>
    </div>
  )
}

export default function HomePage() {
  const navigate = useNavigate()

  return (
    <div className="home-root">
      {/* Hero Section */}
      <section className="home-hero">
        <div className="home-hero-inner">
          <h1 className="home-hero-title">CRAWER WORKFLOW STUDIO</h1>
          <p className="home-hero-subtitle">
            面向浏览器自动化采集的可视化工作台<br />
            支持从工作流设计到脚本生成的全链路编排
          </p>
          <Button
            type="primary"
            size="large"
            className="home-hero-cta"
            onClick={() => navigate('/tasks')}
          >
            进入任务管理
          </Button>
        </div>
        <div className="home-hero-decoration">
          <div className="home-hero-grid" />
        </div>
      </section>

      {/* Feature Showcase */}
      <section className="home-features">
        <div className="home-features-inner">
          <FeatureCard
            tag="VISUAL"
            title="可视化编排"
            description="拖拽节点、直连边线、DSL 编辑器双向同步，所见即所得的流程设计体验"
          />
          <FeatureCard
            tag="AI"
            title="AI 智能生成"
            description="智能推断提取字段、优化选择器、分析分页逻辑，AI 赋能采集工作流"
          />
          <FeatureCard
            tag="TASK"
            title="任务管理"
            description="创建任务、保存资产包、版本管理与批量执行，完整项目周期管理"
          />
        </div>
      </section>

      {/* Dark Technical Workflow Showcase */}
      <section className="home-workflow">
        <div className="home-workflow-inner">
          <div className="home-workflow-header">
            <span className="home-workflow-eyebrow">技术流程</span>
            <h2 className="home-workflow-heading">设计 → 验证 → 生成 → 保存</h2>
            <p className="home-workflow-subtext">
              完整的工作流生命周期，从可视化设计到可执行脚本的自动化流水线
            </p>
          </div>
          <div className="home-workflow-steps">
            <WorkflowStep index={1} label="设计" />
            <div className="home-workflow-arrow">→</div>
            <WorkflowStep index={2} label="验证" />
            <div className="home-workflow-arrow">→</div>
            <WorkflowStep index={3} label="生成" />
            <div className="home-workflow-arrow">→</div>
            <WorkflowStep index={4} label="保存" />
          </div>
        </div>
      </section>
    </div>
  )
}
