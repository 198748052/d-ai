export const metadata = { title: "用户协议" };

export default function TermsPage() {
  return (
    <article className="mx-auto max-w-3xl space-y-5 rounded-xl border border-ink-200 bg-white p-6 shadow-card">
      <h1 className="text-xl font-semibold text-ink-900">用户协议</h1>
      <p className="text-xs text-ink-400">最后更新：2026-11-20</p>

      <section className="space-y-2 text-sm leading-7 text-ink-700">
        <h2 className="font-semibold text-ink-900">一、服务说明</h2>
        <p>
          本平台提供中文学术文本的改写与 AI 特征检测辅助服务。平台按实际提交字数计费，
          注册赠送额度用于体验。用户应在使用前确认自身对提交内容拥有合法使用权。
        </p>

        <h2 className="font-semibold text-ink-900">二、账号与额度</h2>
        <p>
          用户应妥善保管账号与密码，因账号泄露造成的损失由用户自行承担。
          额度可通过兑换码或管理员发放获得，额度不可提现、不可转让。
          任务在未产出任何段落前失败或被取消时，相应额度会退回账户。
        </p>

        <h2 className="font-semibold text-ink-900">三、使用规范</h2>
        <p>
          用户不得利用本平台提交违法违规、侵权、虚假信息或危害国家安全的内容。
          平台有权对违规账号采取限制使用、冻结额度或封禁等措施。
          平台输出结果仅供参考，用户应自行核验事实、数据与引用，并对最终文本负责。
        </p>

        <h2 className="font-semibold text-ink-900">四、服务变更与中断</h2>
        <p>
          平台可能因维护、升级或不可抗力暂停服务。平台会尽力保障数据安全，
          但不承诺服务绝对不中断。建议用户自行保存重要文本。
        </p>

        <h2 className="font-semibold text-ink-900">五、免责声明</h2>
        <p>
          平台不保证改写结果能通过任何特定检测工具，也不对用户使用结果产生的直接或间接损失承担责任。
        </p>

        <h2 className="font-semibold text-ink-900">六、协议更新</h2>
        <p>
          平台可能更新本协议，更新后会在本页面公布。继续使用即视为接受更新后的协议。
        </p>
      </section>
    </article>
  );
}
