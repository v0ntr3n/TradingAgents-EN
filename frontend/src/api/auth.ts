import { ApiClient } from './request'
import type { 
  LoginForm, 
  RegisterForm, 
  LoginResponse, 
  RefreshTokenResponse,
  User,
  UserUpdatePayload,
  ChangePasswordForm
} from '@/types/auth'

export const authApi = {
  // Login
  login: (data: LoginForm) =>
    ApiClient.post<LoginResponse>('/api/auth/login', data, {
      skipAuth: true,  // Login requests do not require authentication
      skipAuthError: true  // Skip automatic handling of 401 errors
    }),

  // Register
  register: (data: RegisterForm) =>
    ApiClient.post('/api/auth/register', data, {
      skipAuth: true,  // Registration requests do not require authentication
      skipAuthError: true  // Skip automatic handling of 401 errors
    }),

  // Log out
  logout: () =>
    ApiClient.post('/api/auth/logout'),

  // Refresh Token
  refreshToken: (refreshToken: string) =>
    ApiClient.post<RefreshTokenResponse>('/api/auth/refresh', { refresh_token: refreshToken }),

  // Get user information
  getUserInfo: () =>
    ApiClient.get<User>('/api/auth/me'),

  // Obtain user permissions (not required for the open source version, admin has all permissions)
  // getUserPermissions: () =>
  //   ApiClient.get<UserPermissions>('/api/auth/permissions'),

  // Update user information
  updateUserInfo: (data: UserUpdatePayload) =>
    ApiClient.put<User>('/api/auth/me', data),

  // Change password
  changePassword: (data: ChangePasswordForm) =>
    ApiClient.post('/api/auth/change-password', data),

  // reset password
  resetPassword: (email: string) =>
    ApiClient.post('/api/auth/reset-password', { email }),

  // Verify email
  verifyEmail: (token: string) =>
    ApiClient.post('/api/auth/verify-email', { token }),

}
