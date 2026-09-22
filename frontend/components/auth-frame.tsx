// SPDX-FileCopyrightText: 2026 Clipo contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ReactNode } from "react";

import { Brand, Icon } from "./icon";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="auth-layout">
      <aside className="auth-story">
        <Brand />
        <div className="story-content">
          <span className="eyebrow">YOUR OWN LITTLE KNOWLEDGE SPACE</span>
          <h1>
            把值得留下的，
            <br />
            好好收起来<span>。</span>
          </h1>
          <p>
            为灵感留一个位置。
            <br />
            从属于自己的知识空间开始。
          </p>
          <div className="story-illustration" aria-hidden="true">
            <div className="paper paper-back" />
            <div className="paper paper-front">
              <span className="paper-label">
                <Icon name="bookmark" size={16} /> A PLACE FOR IDEAS
              </span>
              <div className="paper-title">让信息成为积累。</div>
              <div className="paper-line" />
              <div className="paper-line short" />
              <div className="paper-stamp">
                <Icon name="clip" size={34} />
              </div>
            </div>
            <span className="floating-star">✳</span>
          </div>
        </div>
        <div className="story-footer">
          <Icon name="lock" size={16} /> 自托管 · 数据属于你
        </div>
      </aside>
      <section className="auth-panel">
        <div className="mobile-brand">
          <Brand />
        </div>
        <div className="auth-form-wrap">{children}</div>
        <p className="auth-footer">Clipo · 从收藏，到真正拥有</p>
      </section>
    </main>
  );
}
