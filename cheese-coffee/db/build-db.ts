

console.log(`hello world ${process.cwd()}`);

const targetLocation = process.argv[0];
const sources = process.argv.slice(1);

console.log(`target: ${targetLocation}`);
console.log(`sources: ${sources}`);
console.log(process.execArgv);
