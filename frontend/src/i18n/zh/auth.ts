import type enAuth from '../en/auth';

export default {
  'login': '登录',
  'logging_in': '登录中...',
  'login_failed': '登录失败',
  'username': '用户名',
  'password': '密码',
  'confirm_password': '确认密码',
  'register': '注册账号',
  'registering': '注册中...',
  'registration_failed': '注册失败',
  'password_mismatch': '两次输入的密码不一致',
  'no_account_register': '没有账号？去注册',
  'already_have_account': '已有账号？去登录',
} satisfies Record<keyof typeof enAuth, string>;
