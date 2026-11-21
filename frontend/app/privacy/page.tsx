export const metadata = { title: "隐私政策" };

export default function PrivacyPage() {
  return (
    <article className="mx-auto max-w-3xl space-y-5 rounded-xl border border-ink-200 bg-white p-6 shadow-card">
      <h1 className="text-xl font-semibold text-ink-900">隐私政策</h1>
      <p className="text-xs text-ink-400">最后更新：2026-11-20</p>

      <section className="space-y-2 text-sm leading-7 text-ink-700">
        <h2 className="font-semibold text-ink-900">一、我们收集的信息</h2>
        <p>
          注册与登录：QQ 邮箱地址、密码哈希、昵称、注册与登录时间。
          使用过程：提交的文本、改写结果、任务状态、消耗字数与额度流水。
          技术信息：IP 地址（用于验证码限流与安全审计）、浏览器错误信息。
        </p>

        <h2 className="font-semibold text-ink-900">二、信息用途</h2>
        <p>
          用于账号登录、按字数计费、任务记录展示、问题排查与安全防护。
          我们不会将用户提交的文本用于训练模型，也不会向无关第三方出售用户数据。
        </p>

        <h2 className="font-semibold text-ink-900">三、第三方服务</h2>
        <p>
          改写过程会把文本片段发送给平台配置的大语言模型服务商以生成结果；
          邮箱验证码通过 SMTP 邮件服务发送。第三方服务商按其自身隐私政策处理数据。
        </p>

        <h2 className="font-semibold text-ink-900">四、数据存储与保护</h2>
        <p>
          数据存储于平台服务器的数据库中，密码使用加盐哈希保存，接口密钥加密保存。
          我们采取访问控制与日志审计措施，但无法保证绝对安全。
        </p>

        <h2 className="font-semibold text-ink-900">五、数据保留与删除</h2>
        <p>
          任务记录与额度流水在账号存续期间保留。用户可以联系管理员申请删除账号及相关数据。
        </p>

        <h2 className="font-semibold text-ink-900">六、联系我们</h2>
        <p>如对本政策有疑问，请通过平台管理员邮箱联系。</p>
      </section>
    </article>
  );
}
