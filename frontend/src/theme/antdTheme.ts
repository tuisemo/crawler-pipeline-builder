import { theme, type ThemeConfig } from 'antd'

/**
 * Ant Design Theme Configuration: Compact Mission Control
 * Aligned with DESIGN.md — pure black/gray system.
 * Uses #000000 (Pure Black) as the primary brand accent.
 */
export const antdTheme: ThemeConfig = {
  token: {
    // Typography
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue", Helvetica, Arial, sans-serif',
    fontSize: 14,

    // Foundation (DESIGN.md)
    colorPrimary: '#000000',        // Pure Black
    colorInfo: '#000000',
    colorSuccess: '#16A34A',        // Verified Green
    colorWarning: '#F59E0B',        // Caution Amber
    colorError: '#DC2626',          // Fault Red

    // Backgrounds
    colorBgBase: '#FFFFFF',         // Canvas
    colorBgLayout: '#FFFFFF',       // Canvas
    colorBgContainer: '#FFFFFF',    // Canvas
    colorBgElevated: '#FFFFFF',

    // Text
    colorText: '#000000',           // Ink
    colorTextSecondary: '#525252',  // Charcoal
    colorTextTertiary: '#737373',   // Body
    colorTextQuaternary: '#a3a3a3', // Mute

    // Borders & Shadows — hairline system
    colorBorder: '#e5e5e5',         // Hairline
    colorBorderSecondary: '#d4d4d4', // Hairline Strong
    borderRadius: 6,                // Keep existing compact corners
    borderRadiusSM: 4,
    borderRadiusLG: 12,             // Cards
    borderRadiusXS: 2,

    // Interactive
    colorLink: '#000000',
    colorLinkHover: '#525252',
    controlHeight: 28,

    // Shadows — minimal application depth
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
    boxShadowSecondary: '0 4px 12px rgba(0, 0, 0, 0.06)',
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
      colorBorderSecondary: '#e5e5e5',
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
      headerBg: '#fafafa',          // Soft Surface (was blue-tinted #EFF6FF)
      headerColor: '#525252',       // Charcoal
      headerBorderRadius: 6,
      borderRadius: 8,
      fontSize: 14,
    },
    Tag: {
      borderRadiusSM: 6,
      fontSize: 13,
    },
    Tabs: {
      fontWeightStrong: 700,
      itemSelectedColor: '#000000',
      inkBarColor: '#000000',
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

