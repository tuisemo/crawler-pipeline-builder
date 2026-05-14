import { theme, type ThemeConfig } from 'antd'

/**
 * Ant Design Theme Configuration: Compact Mission Control
 * Strictly aligned with DESIGN.md and user feedback.
 * Uses #0F172A (Ink Black) as the primary technical accent.
 */
export const antdTheme: ThemeConfig = {
  token: {
    // Typography
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue", Helvetica, Arial, sans-serif',
    fontSize: 14,

    // Foundation (DESIGN.md Section 3)
    colorPrimary: '#0F172A',        // Ink Black
    colorInfo: '#0F172A',
    colorSuccess: '#16A34A',        // Verified Green
    colorWarning: '#F59E0B',        // Caution Amber
    colorError: '#DC2626',          // Fault Red

    // Backgrounds
    colorBgBase: '#FFFFFF',         // Ice Surface
    colorBgLayout: '#FFFFFF',       // Ice Surface
    colorBgContainer: '#FFFFFF',    // Ice Surface
    colorBgElevated: '#FFFFFF',

    // Text
    colorText: '#0F172A',
    colorTextSecondary: '#334155',
    colorTextTertiary: '#64748B',

    // Borders & Shadows
    colorBorder: '#E2E8F0',
    colorBorderSecondary: '#CBD5E1',
    borderRadius: 6,                // Compact sharp corners
    borderRadiusSM: 4,
    borderRadiusLG: 10,
    borderRadiusXS: 2,

    // Interactive
    colorLink: '#0F172A',
    colorLinkHover: '#334155',
    controlHeight: 28,               // Global compact control height

    // Custom Box Shadows
    boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.02)',
    boxShadowSecondary: '0 8px 24px rgba(15, 23, 42, 0.06)',
  },
  components: {
    Button: {
      fontWeight: 500,
      controlHeight: 32,
      paddingInline: 16,
      borderRadius: 6,
      fontSize: 14,
    },
    Card: {
      borderRadiusLG: 12,
      colorBorderSecondary: 'rgba(15, 23, 42, 0.06)',
    },
    Input: {
      borderRadius: 6,
      controlHeight: 32,
      fontSize: 14,
    },
    InputNumber: {
      borderRadius: 6,
      controlHeight: 32,
      fontSize: 14,
    },
    Select: {
      borderRadius: 6,
      controlHeight: 32,
      fontSize: 14,
    },
    Table: {
      headerBg: '#EFF6FF',
      headerColor: '#334155',
      headerBorderRadius: 6,
      borderRadius: 8,
      fontSize: 14,
    },
    Tag: {
      borderRadiusSM: 9999,
      fontSize: 13,
    },
    Tabs: {
      fontWeightStrong: 700,
      itemSelectedColor: '#0F172A',
      inkBarColor: '#0F172A',
      fontSize: 14,
    },
    Collapse: {
      borderRadiusLG: 8,
    },
    Modal: {
      borderRadiusLG: 12,
      fontSize: 14,
    },
    Drawer: {
      colorBgContainer: '#FFFFFF',
    },
    Alert: {
      borderRadiusLG: 8,
      fontSize: 14,
    },
    Menu: {
      itemBorderRadius: 6,
      fontSize: 14,
    },
    Checkbox: {
      fontSize: 14,
    },
    Radio: {
      fontSize: 14,
    },
    Switch: {
      fontSize: 14,
    },
    Tooltip: {
      fontSize: 13,
    },
    Popover: {
      fontSize: 14,
    },
    Form: {
      fontSize: 14,
    },
    List: {
      fontSize: 14,
    },
    Pagination: {
      fontSize: 14,
    },
    Breadcrumb: {
      fontSize: 14,
    },
    Steps: {
      fontSize: 14,
    },
    Tree: {
      fontSize: 14,
    },
    Timeline: {
      fontSize: 14,
    },
    Descriptions: {
      fontSize: 14,
    },
  },
}
