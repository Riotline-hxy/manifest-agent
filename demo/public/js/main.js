// 入口：挂载外壳。
import { mount } from "./app.js";
import { registerSW } from "./push.js";

registerSW();

const el = document.getElementById("app");
mount(el);
