import { useEffect, useRef, useState } from 'react'
import { Button, Space, Typography, Card, Statistic, Row, Col } from 'antd'
import { useNavigate } from 'react-router-dom'
import { 
  ArrowRightOutlined, 
  ThunderboltFilled, 
  SafetyCertificateOutlined, 
  GithubOutlined,
  TwitterOutlined,
  GlobalOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  AreaChartOutlined,
  BarChartOutlined
} from '@ant-design/icons'

const { Title, Text } = Typography

// ── Simple Tech Canvas ──
const GridBackground = () => (
  <div style={{ 
    position: 'absolute', 
    inset: 0, 
    zIndex: 0, 
    backgroundImage: 'linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px)',
    backgroundSize: '40px 40px',
    maskImage: 'radial-gradient(circle at center, black, transparent 80%)',
    pointerEvents: 'none'
  }} />
)

import { TechScene } from '../components/TechScene'

export default function HomePage() {
  const navigate = useNavigate()

  return (
    <div className="home-root" style={{ background: '#fff', overflow: 'hidden' }}>
      <GridBackground />

      {/* ── Split Hero Section ── */}
      <section style={{ 
        minHeight: '72vh', 
        display: 'flex', 
        alignItems: 'center', 
        padding: '0 80px',
        position: 'relative',
        zIndex: 1
      }}>
        <div style={{ flex: 1, maxWidth: 640 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
             <span className="home-hero-eyebrow" style={{ color: 'var(--sd-color-primary)', fontWeight: 600, letterSpacing: '0.2em' }}>CRAWLER WORKFLOW V1.0</span>
             <div style={{ width: 40, height: 1, background: '#eee' }} />
             <span className="mono" style={{ color: '#ccc', fontSize: 10, letterSpacing: '0.1em' }}>INDUSTRIAL_GRADE_AUTOMATION</span>
          </div>
          
          <Title style={{ fontSize: 84, lineHeight: 1.1, margin: '16px 0', letterSpacing: '-0.02em', fontWeight: 800 }}>
            驱动数据<br />
            <span style={{ color: 'var(--sd-color-text-tertiary)' }}>探索无限可能.</span>
          </Title>
          
          <div style={{ marginBottom: 40 }}>
             <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 12, fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
                PRECISION. EFFICIENCY. SCALABILITY.
             </div>
             <Text style={{ fontSize: 19, color: '#666', display: 'block', lineHeight: 1.8 }}>
                新一代可视化浏览器自动化工作站。利用 AI 驱动的精准识别技术，<br />
                为您构建稳健、高效且可扩展的数据资产生产链。
             </Text>
          </div>

          <Space size={24}>
            <Button 
              type="primary" 
              size="large" 
              onClick={() => navigate('/tasks')}
              style={{ height: 52, padding: '0 40px', fontSize: 18, background: '#000', border: 'none', borderRadius: 8, fontWeight: 600 }}
            >
              进入工作站 <ArrowRightOutlined />
            </Button>
            <Button 
              size="large" 
              style={{ height: 52, padding: '0 32px', fontSize: 18, border: '1px solid #ddd', borderRadius: 8 }}
            >
              <GithubOutlined /> Explore OSS
            </Button>
          </Space>
        </div>

        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
           <TechScene />
        </div>
      </section>

      {/* ── Minimal Bento Grid (Compressed) ── */}
      <section style={{ padding: '20px 80px', background: '#fdfdfd', borderTop: '1px solid #eee' }}>
        <Row gutter={[32, 32]}>
          <Col span={8}>
            <div style={{ padding: '8px 0' }}>
              <DeploymentUnitOutlined style={{ fontSize: 24, color: 'var(--sd-color-info)', marginBottom: 12 }} />
              <Title level={4} style={{ fontSize: 18, marginBottom: 8 }}>可视化工作流</Title>
              <Text style={{ fontSize: 13, color: '#777', lineHeight: 1.6 }}>
                通过直观的节点图编排采集逻辑，支持无限嵌套与条件分支。
              </Text>
            </div>
          </Col>
          <Col span={8}>
            <div style={{ padding: '8px 0' }}>
              <ThunderboltFilled style={{ fontSize: 24, color: 'var(--sd-color-warning)', marginBottom: 12 }} />
              <Title level={4} style={{ fontSize: 18, marginBottom: 8 }}>AI 智能赋能</Title>
              <Text style={{ fontSize: 13, color: '#777', lineHeight: 1.6 }}>
                自动识别页面结构，针对变体页面具备极强的鲁棒性与自适应修复能力。
              </Text>
            </div>
          </Col>
          <Col span={8}>
            <div style={{ padding: '8px 0' }}>
              <DatabaseOutlined style={{ fontSize: 24, color: '#000', marginBottom: 12 }} />
              <Title level={4} style={{ fontSize: 18, marginBottom: 8 }}>资产版本管理</Title>
              <Text style={{ fontSize: 13, color: '#777', lineHeight: 1.6 }}>
                所有采集规则与脚本均支持版本回溯与云端资产同步，确保数据链条稳定。
              </Text>
            </div>
          </Col>
        </Row>
      </section>

      {/* ── Simplified Footer ── */}
      <footer style={{ padding: '20px 80px', borderTop: '1px solid #eee', background: '#fff' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div className="mono" style={{ fontWeight: 700, fontSize: 14, letterSpacing: '0.1em' }}>SCRAPER FLOW STUDIO</div>
            <div style={{ color: '#999', marginTop: 4, fontSize: 11 }}>© 2026 海量数据工作站 (SEA DATA WORKBENCH). 保留所有权利.</div>
          </div>
          <Space size={40}>
            <a href="#" style={{ color: '#999', fontSize: 12 }}>文档中心</a>
            <a href="#" style={{ color: '#999', fontSize: 12 }}>企业方案</a>
            <a href="#" style={{ color: '#999', fontSize: 12 }}>GITHUB</a>
          </Space>
        </div>
      </footer>
    </div>
  )
}
