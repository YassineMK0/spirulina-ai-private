// Manual mock for tests: react-markdown v9 is ESM-only and not needed for
// component behavior assertions here (no test checks parsed markdown
// structure) -- render children as-is instead of fighting Jest's ESM
// transform config for the whole remark/unified dependency tree.
module.exports = function ReactMarkdown({ children }) {
  return children;
};
