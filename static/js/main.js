/** 应用入口：创建并挂载工作台。 */

import { Workbench } from './workbench.js';

function bootstrap() {
  const workbench = new Workbench();
  workbench.mount();
  // 便于调试：window.rfDeembed.workbench
  window.rfDeembed = { workbench };
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
} else {
  bootstrap();
}
