// User information interface
export interface User {
  id: string
  username: string
  email: string
  avatar?: string
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  created_at: string
  updated_at: string
  last_login?: string
  
  // User preferences
  preferences: UserPreferences
  
  // Quotas and limits
  daily_quota: number
  concurrent_limit: number
  
  // Statistics
  total_analyses: number
  successful_analyses: number
  failed_analyses: number
}

export interface AssistantSettings {
  name?: string
  tone?: string
  custom_instructions?: string
}

// User preferences
export interface UserPreferences {
  // Analyze preferences
  default_market: 'A shares'
  default_depth: '1' | '2' | '3' | '4' | '5'  // 1-5 level analysis depth
  default_analysts?: string[]  // Default analyst list: market analysts, fundamental analysts, news analysts, social media analysts
  auto_refresh?: boolean
  refresh_interval?: number
  risk_preference?: 'conservative' | 'neutral' | 'aggressive'  // Risk Appetite: Conservative/Neutral/Aggressive

  // Appearance settings
  ui_theme: 'light' | 'dark' | 'auto'
  sidebar_width?: number

  // language and region
  language: 'zh-CN' | 'en-US'

  // Notification settings
  notifications_enabled: boolean
  email_notifications: boolean
  desktop_notifications?: boolean
  analysis_complete_notification?: boolean
  system_maintenance_notification?: boolean
  assistant_settings?: AssistantSettings
}

export interface UserUpdatePayload extends Partial<Omit<User, 'preferences'>> {
  preferences?: Partial<UserPreferences>
}

// Login form
export interface LoginForm {
  username: string
  password: string
  remember_me?: boolean
  captcha?: string
}

// Registration form
export interface RegisterForm {
  username: string
  email: string
  password: string
  confirm_password: string
  agreement: boolean
  captcha?: string
  invitation_code?: string
}

// Change password form
export interface ChangePasswordForm {
  old_password: string
  new_password: string
  confirm_password: string
}

// Reset password form
export interface ResetPasswordForm {
  email: string
  captcha?: string
}

// User permission information
export interface UserPermissions {
  permissions: string[]
  roles: string[]
}

// Login response
export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

// Token refresh response
export interface RefreshTokenResponse {
  access_token: string
  refresh_token?: string
  expires_in: number
}

// User session information
export interface UserSession {
  session_id: string
  user_id: string
  created_at: string
  expires_at: string
  last_activity: string
  ip_address?: string
  user_agent?: string
}

// User statistics
export interface UserStats {
  total_analyses: number
  successful_analyses: number
  failed_analyses: number
  success_rate: number
  daily_quota: number
  daily_used: number
  concurrent_limit: number
  current_concurrent: number
}

// User activity log
export interface UserActivity {
  id: string
  user_id: string
  action: string
  resource: string
  details?: Record<string, any>
  ip_address?: string
  user_agent?: string
  created_at: string
}

// User configuration update
export interface UserConfigUpdate {
  preferences?: Partial<UserPreferences>
  daily_quota?: number
  concurrent_limit?: number
}

// Verification code information
export interface CaptchaInfo {
  captcha_id: string
  captcha_image: string
  expires_in: number
}

// Invitation code information
export interface InvitationCode {
  code: string
  created_by: string
  used_by?: string
  used_at?: string
  expires_at: string
  is_used: boolean
  max_uses: number
  current_uses: number
}
