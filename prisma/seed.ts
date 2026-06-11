import "dotenv/config";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main(): Promise<void> {
  const name = process.env.SERVER_NAME ?? "Default";
  const baseUrl = process.env.SERVER_BASE_URL;
  const adminPath = process.env.SERVER_ADMIN_PATH ?? "/";
  const username = process.env.SERVER_USERNAME;
  const password = process.env.SERVER_PASSWORD;
  const inboundId = Number(process.env.SERVER_INBOUND_ID ?? "1");
  const region = process.env.SERVER_REGION ?? "RU";

  if (!baseUrl || !username || !password) {
    console.log("Skip seed: set SERVER_BASE_URL, SERVER_USERNAME, SERVER_PASSWORD");
    return;
  }

  const existing = await prisma.server.findFirst({ where: { name } });
  if (existing) {
    console.log(`Server "${name}" already exists (id=${existing.id})`);
    return;
  }

  const server = await prisma.server.create({
    data: {
      name,
      baseUrl,
      adminPath,
      username,
      password,
      inboundId,
      region,
      isActive: true,
    },
  });

  console.log(`Created server "${server.name}" (id=${server.id})`);
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
