import { Button, Space, Row, Col } from 'antd'
import { useNavigate } from 'react-router-dom'
import './HomePage.css'
import { 
  ArrowRightOutlined, 
  ThunderboltFilled, 
  GithubOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  LoginOutlined
} from '@ant-design/icons'
import { useAuth } from '../auth/useAuth'
import { getPublicAssetUrl } from '../utils/assetUrl'

const GridBackground = () => (
  <div style={{ 
    position: 'absolute', 
    inset: 0, 
    zIndex: 0, 
    backgroundImage: 'linear-gradient(rgba(0,0,0,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.05) 1px, transparent 1px)',
    backgroundSize: '60px 60px',
    maskImage: 'radial-gradient(ellipse 80% 70% at 60% 40%, black, transparent)',
    pointerEvents: 'none'
  }} />
)

const GlowOrb = ({ color, size, top, left }: { color: string; size: number; top: string; left: string }) => (
  <div style={{
    position: 'absolute',
    top,
    left,
    width: size,
    height: size,
    background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
    filter: 'blur(80px)',
    opacity: 0.4,
    pointerEvents: 'none',
    zIndex: 0,
  }} />
)

import { TechScene } from '../components/TechScene'

export default function HomePage() {
  const navigate = useNavigate()
  const { isAuthenticated, isLoading, login } = useAuth()
  const logoUrl = getPublicAssetUrl('logo.svg')

  return (
    <div className="home-root" style={{ background: '#FFFFFF', overflow: 'hidden' }}>
      <GridBackground />
      <GlowOrb color="rgba(15,23,42,0.08)" size={600} top="-10%" left="50%" />
      <GlowOrb color="rgba(6,182,212,0.06)" size={400} top="50%" left="20%" />

      {/* ── Hero Section ── */}
      <section style={{ 
        minHeight: '78vh', 
        display: 'flex', 
        alignItems: 'center', 
        padding: '0 80px',
        position: 'relative',
        zIndex: 1
      }}>
        <div style={{ flex: 1, maxWidth: 620 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
             <span style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--sd-color-text-tertiary)', letterSpacing: '0.15em' }}>
               ADVANCED WEB SCRAPING INFRASTRUCTURE
             </span>
          </div>
          
          <h1 style={{ fontFamily: '"Inter", var(--sd-font-ui)', fontSize: 64, lineHeight: 1.05, margin: '0 0 24px', letterSpacing: '-0.035em', fontWeight: 800, color: '#0F172A' }}>
            驱动数据
            <br />
            <span style={{ color: '#94A3B8' }}>探索无限可能.</span>
          </h1>
          
          <div style={{ marginBottom: 40 }}>
             <p style={{ fontSize: 17, color: '#475569', lineHeight: 1.8, margin: 0 }}>
                新一代可视化浏览器自动化工作站。利用 AI 驱动的精准识别技术，
                为您构建稳健、高效且可扩展的数据资产生产链。
             </p>
          </div>

          <Space size={16}>
            <Button 
              type="primary" 
              size="large" 
              onClick={() => navigate('/tasks')}
              style={{ height: 48, padding: '0 32px', fontSize: 15, background: '#0F172A', border: 'none', borderRadius: 10, fontWeight: 600 }}
            >
              进入工作站 <ArrowRightOutlined />
            </Button>
            {!isLoading && !isAuthenticated && (
              <Button 
                size="large" 
                icon={<LoginOutlined />}
                onClick={() => login('/tasks')}
                style={{ height: 48, padding: '0 28px', fontSize: 15, border: '1.5px solid #CBD5E1', borderRadius: 10, fontWeight: 500, background: '#fff' }}
              >
                登录
              </Button>
            )}
            <Button 
              size="large" 
              style={{ height: 48, padding: '0 28px', fontSize: 15, border: '1.5px solid #CBD5E1', borderRadius: 10, fontWeight: 500, background: '#fff' }}
            >
              <GithubOutlined /> Explore OSS
            </Button>
          </Space>
        </div>

        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
           <TechScene />
        </div>
      </section>

      {/* ── Feature Cards ── */}
      <section style={{ padding: '32px 80px 48px', position: 'relative', zIndex: 1 }}>
        <Row gutter={[24, 24]}>
          <Col span={8}>
            <div style={{
              padding: 32,
              background: '#fff',
              borderRadius: 16,
              border: '1px solid #E2E8F0',
              transition: 'all 0.25s ease',
            }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(6,182,212,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                <DeploymentUnitOutlined style={{ fontSize: 22, color: '#06B6D4' }} />
              </div>
              <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', margin: '0 0 8px' }}>可视化工作流</h3>
              <p style={{ fontSize: 14, color: '#64748B', lineHeight: 1.7, margin: 0 }}>
                通过直观的节点图编排采集逻辑，支持无限嵌套与条件分支。
              </p>
            </div>
          </Col>
          <Col span={8}>
            <div style={{
              padding: 32,
              background: '#fff',
              borderRadius: 16,
              border: '1px solid #E2E8F0',
            }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(245,158,11,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                <ThunderboltFilled style={{ fontSize: 22, color: '#F59E0B' }} />
              </div>
              <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', margin: '0 0 8px' }}>AI 智能赋能</h3>
              <p style={{ fontSize: 14, color: '#64748B', lineHeight: 1.7, margin: 0 }}>
                自动识别页面结构，针对变体页面具备极强的鲁棒性与自适应修复能力。
              </p>
            </div>
          </Col>
          <Col span={8}>
            <div style={{
              padding: 32,
              background: '#fff',
              borderRadius: 16,
              border: '1px solid #E2E8F0',
            }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(15,23,42,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                <DatabaseOutlined style={{ fontSize: 22, color: '#0F172A' }} />
              </div>
              <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', margin: '0 0 8px' }}>资产版本管理</h3>
              <p style={{ fontSize: 14, color: '#64748B', lineHeight: 1.7, margin: 0 }}>
                所有采集规则与脚本均支持版本回溯与云端资产同步，确保数据链条稳定。
              </p>
            </div>
          </Col>
        </Row>
      </section>

      {/* ── Footer ── */}
      <footer style={{ padding: '24px 80px', borderTop: '1px solid #E2E8F0', background: '#fff', position: 'relative', zIndex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <img src={logoUrl} alt="SFS" style={{ width: 18, height: 18, borderRadius: 4 }} />
              <span className="mono" style={{ fontWeight: 700, fontSize: 13, letterSpacing: '0.08em', color: '#0F172A' }}>SCRAPER FLOW STUDIO</span>
            </div>
            <span style={{ color: '#CBD5E1', fontSize: 12 }}>© 2026 SEA DATA WORKBENCH</span>
          </div>
          <Space size={32}>
            <a href="#" style={{ color: '#64748B', fontSize: 13, fontWeight: 500, textDecoration: 'none' }}>文档中心</a>
            <a href="#" style={{ color: '#64748B', fontSize: 13, fontWeight: 500, textDecoration: 'none' }}>企业方案</a>
            <a href="#" style={{ color: '#64748B', fontSize: 13, fontWeight: 500, textDecoration: 'none' }}>GITHUB</a>
          </Space>
        </div>
      </footer>
    </div>
  )
}
