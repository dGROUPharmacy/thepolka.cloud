(() => {
  const source = document.getElementById("apex-source");
  const output = document.getElementById("apex-output");
  const diagnostics = document.getElementById("apex-diagnostics");
  const starter = document.getElementById("apex-starter");
  const lineCount = document.getElementById("apex-lines");

  const starters = {
    hello: `public class PolkaHello {
  public static void greet() {
    String visitor = 'builder';
    Integer lessons = 3;
    lessons += 1;
    System.debug('Hello, ' + visitor);
    System.debug('Lessons completed: ' + lessons);
  }
}`,
    score: `public class LeadScore {
  public static void calculate() {
    Integer visits = 7;
    Integer score = 35;
    score += 20;
    System.debug('Visits: ' + visits);
    if (score >= 50) {
      System.debug('Qualified lead');
    }
    System.debug('Score: ' + score);
  }
}`,
    collections: `public class TopicList {
  public static void build() {
    List<String> topics = new List<String>{'Java', 'Apex', 'Testing'};
    System.debug('Topics: ' + topics);
    System.debug('Count: ' + topics.size());
  }
}`,
    trigger: `trigger ContactWelcome on Contact (after insert) {
  // Anatomy lesson only: genuine triggers require Salesforce records.
  Integer received = 2;
  System.debug('Trigger records: ' + received);
}`
  };

  const javaCompanions = {
    hello: `public class PolkaHello {\n  public static void main(String[] args) {\n    String visitor = "builder";\n    int lessons = 4;\n    System.out.println("Hello, " + visitor);\n    System.out.println("Lessons completed: " + lessons);\n  }\n}`,
    score: `public class LeadScore {\n  public static void main(String[] args) {\n    int visits = 7;\n    int score = 55;\n    System.out.println("Visits: " + visits);\n    if (score >= 50) System.out.println("Qualified lead");\n    System.out.println("Score: " + score);\n  }\n}`,
    collections: `import java.util.List;\npublic class TopicList {\n  public static void main(String[] args) {\n    List<String> topics = List.of("Java", "Apex", "Testing");\n    System.out.println("Topics: " + topics);\n    System.out.println("Count: " + topics.size());\n  }\n}`,
    trigger: `// Java has no direct trigger equivalent.\n// Use an event listener or service method in your application.\npublic class ContactWelcome {\n  public void afterInsert(int received) {\n    System.out.println("Event records: " + received);\n  }\n}`
  };

  function refreshLines() {
    lineCount.textContent = `${source.value.split("\\n").length} lines`;
  }

  function splitExpression(expression) {
    return expression.split(/\s*\+\s*/).map(part => part.trim());
  }

  function renderValue(token, variables) {
    if (/^'.*'$/.test(token)) return token.slice(1, -1);
    if (/^-?\d+$/.test(token)) return Number(token);
    const size = token.match(/^([A-Za-z_]\w*)\.size\(\)$/);
    if (size) return Array.isArray(variables[size[1]]) ? variables[size[1]].length : 0;
    if (Object.prototype.hasOwnProperty.call(variables, token)) {
      return Array.isArray(variables[token]) ? `[${variables[token].join(", ")}]` : variables[token];
    }
    return token;
  }

  function simulate(code) {
    const notes = [];
    const logs = [];
    const variables = {};
    const opens = (code.match(/{/g) || []).length;
    const closes = (code.match(/}/g) || []).length;
    if (opens !== closes) notes.push({ kind: "error", text: `Brace mismatch: ${opens} opening and ${closes} closing braces.` });
    if (!/\b(class|trigger)\b/.test(code)) notes.push({ kind: "error", text: "Add a class or trigger declaration." });
    if (/ArrayList|HashMap|System\.out\.println/.test(code)) notes.push({ kind: "warn", text: "Java-specific API detected. Translate it to List, Map, or System.debug for Apex." });
    if (/\[(?:SELECT|FIND)\b/i.test(code)) notes.push({ kind: "info", text: "SOQL/SOSL recognized but not executed outside an authenticated Salesforce org." });
    if (/\b(insert|update|upsert|delete)\b\s+/i.test(code)) notes.push({ kind: "info", text: "DML recognized but intentionally disabled in this independent simulator." });

    for (const raw of code.split("\n")) {
      const line = raw.trim();
      let match = line.match(/^(String|Integer|Decimal|Boolean)\s+([A-Za-z_]\w*)\s*=\s*(.+);$/);
      if (match) {
        const [, type, name, value] = match;
        if (type === "String") variables[name] = value.replace(/^'|'$/g, "");
        if (type === "Integer" || type === "Decimal") variables[name] = Number(value);
        if (type === "Boolean") variables[name] = value.toLowerCase() === "true";
      }
      match = line.match(/^List<String>\s+([A-Za-z_]\w*)\s*=\s*new List<String>\{(.*)\};$/);
      if (match) variables[match[1]] = [...match[2].matchAll(/'([^']*)'/g)].map(item => item[1]);
      match = line.match(/^([A-Za-z_]\w*)\s*\+=\s*(-?\d+);$/);
      if (match && typeof variables[match[1]] === "number") variables[match[1]] += Number(match[2]);
    }

    let activeCondition = true;
    for (const raw of code.split("\n")) {
      const line = raw.trim();
      const condition = line.match(/^if\s*\(\s*([A-Za-z_]\w*)\s*(>=|<=|==|>|<)\s*(-?\d+)\s*\)\s*\{$/);
      if (condition) {
        const left = Number(variables[condition[1]]);
        const right = Number(condition[3]);
        activeCondition = ({">=": left >= right, "<=": left <= right, "==": left === right, ">": left > right, "<": left < right})[condition[2]];
        continue;
      }
      if (line === "}") activeCondition = true;
      const debug = line.match(/^System\.debug\((.*)\);$/);
      if (debug && activeCondition) logs.push(splitExpression(debug[1]).map(token => renderValue(token, variables)).join(""));
    }

    if (!notes.some(note => note.kind === "error")) notes.push({ kind: "ok", text: "Structure accepted by the safe teaching subset. Validate genuine Apex in a Salesforce org." });
    return { logs, notes, variables };
  }

  function run() {
    const result = simulate(source.value);
    output.textContent = result.logs.length ? result.logs.map(line => `DEBUG | ${line}`).join("\n") : "No System.debug output produced.";
    diagnostics.innerHTML = result.notes.map(note => `<p class="${note.kind}">${note.text}</p>`).join("");
  }

  function review() {
    const result = simulate(source.value);
    const facts = [
      `Variables detected: ${Object.keys(result.variables).length}`,
      `Debug statements: ${(source.value.match(/System\.debug/g) || []).length}`,
      `Database operations: ${(source.value.match(/\b(insert|update|upsert|delete)\b/gi) || []).length}`,
      `Queries: ${(source.value.match(/\[(SELECT|FIND)\b/gi) || []).length}`
    ];
    output.textContent = `TRANSLATION REVIEW\n${facts.join("\n")}\n\nNext: test sharing, permissions, bulk behavior, limits, and coverage in a real Developer org.`;
    diagnostics.innerHTML = result.notes.map(note => `<p class="${note.kind}">${note.text}</p>`).join("");
  }

  function download(name, content, type = "text/plain") {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([content], { type }));
    link.download = name;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function widgetDocument() {
    const escaped = source.value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<!doctype html><meta charset="utf-8"><title>Polka Apex Micro Widget</title>
<style>body{margin:0;padding:24px;background:#081522;color:#d9fffb;font:16px system-ui}.widget{max-width:760px;margin:auto;padding:24px;border:1px solid #42d7c8;border-radius:24px;background:#0e2234}pre{white-space:pre-wrap;padding:18px;border-radius:14px;background:#06101a;color:#b7f5ed}small{color:#91aeb5}</style>
<section class="widget"><h1>Apex Micro Widget</h1><p>An inspectable source card created at ThePolka.Cloud.</p><pre>${escaped}</pre><small>Educational source only. Genuine Apex requires validation and execution on the Salesforce Platform.</small></section>`;
  }

  starter.addEventListener("change", () => {
    source.value = starters[starter.value];
    output.textContent = "Starter loaded. Select Run safe simulation.";
    diagnostics.innerHTML = "";
    refreshLines();
  });
  source.addEventListener("input", refreshLines);
  document.getElementById("apex-run").addEventListener("click", run);
  document.getElementById("apex-review").addEventListener("click", review);
  document.getElementById("apex-download").addEventListener("click", () => download(`${starter.value}.cls`, source.value));
  document.getElementById("java-download").addEventListener("click", () => download(`${starter.value}.java`, javaCompanions[starter.value]));
  document.getElementById("widget-download").addEventListener("click", () => download("apex-micro-widget.html", widgetDocument(), "text/html"));

  source.value = starters.hello;
  refreshLines();
})();
