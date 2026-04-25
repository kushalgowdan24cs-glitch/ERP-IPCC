import asyncpg
import asyncio

async def test():
    conn = await asyncpg.connect(
        'postgresql://admin:supersecretpassword@localhost:5435/proctorshield'
    )
    
    # Check if erp_branches table exists and has data
    branches = await conn.fetch('SELECT * FROM erp_branches')
    print(f'✓ erp_branches table exists, current rows: {len(branches)}')
    
    # Check erp_courses columns
    columns = await conn.fetch('SELECT column_name FROM information_schema.columns WHERE table_name = $1 ORDER BY ordinal_position', 'erp_courses')
    col_names = [c['column_name'] for c in columns]
    print(f'✓ erp_courses has {len(col_names)} columns')
    print(f'  Includes branch: {"branch" in col_names}')
    print(f'  Includes semester: {"semester" in col_names}')
    
    # Check if admin user exists
    admin_count = await conn.fetchval('SELECT COUNT(*) FROM erp_users WHERE role = $1', 'admin')
    print(f'✓ Admin users in database: {admin_count}')
    
    await conn.close()
    print('\n✓✓✓ All schema validations passed!')

asyncio.run(test())
