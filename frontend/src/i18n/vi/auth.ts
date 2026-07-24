import type enAuth from "@/i18n/en/auth";

export default {
  'login': 'Đăng nhập',
  'logging_in': 'Đang đăng nhập...',
  'login_failed': 'Đăng nhập thất bại',
  'username': 'Tên đăng nhập',
  'password': 'Mật khẩu',
  'confirm_password': 'Xác nhận mật khẩu',
  'register': 'Tạo tài khoản',
  'registering': 'Đang tạo tài khoản...',
  'registration_failed': 'Đăng ký thất bại',
  'password_mismatch': 'Mật khẩu xác nhận không khớp',
  'no_account_register': 'Chưa có tài khoản? Tạo tài khoản',
  'already_have_account': 'Đã có tài khoản? Đăng nhập',
} satisfies Record<keyof typeof enAuth, string>;
