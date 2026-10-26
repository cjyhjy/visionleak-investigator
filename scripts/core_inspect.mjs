// Fixed local API bridge; no detector or report identity reimplementation.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
const [corePath, reportPath] = process.argv.slice(2);
const base=pathToFileURL(resolve(corePath)+'/');
const {verifyReportIdentity}=await import(new URL('demo/report-identity.mjs',base));
const {validateReport}=await import(new URL('demo/review-validation.mjs',base));
const {workflow}=await import(new URL('tools/workflow.mjs',base));
const raw=JSON.parse(readFileSync(reportPath,'utf8'));
await verifyReportIdentity(raw);validateReport(raw);
console.log(JSON.stringify({auditId:raw.auditId, report_identity:'valid', verification_ids:workflow({operation:'verificationInputs',report:raw}).ids}));
