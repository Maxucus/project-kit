import { createServer } from 'node:http';

const server = createServer((request, response) => {
  const healthy = request.method === 'GET' && request.url === '/health';
  response.writeHead(healthy ? 200 : 404, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(healthy ? { status: 'ok' } : { error: 'not found' }));
});
server.listen(Number(process.env.PORT ?? 3000), '127.0.0.1', () => {
  console.log(server.address().port);
});
