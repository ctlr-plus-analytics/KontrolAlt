-- Create an admin user with email 'admin@kontrolalt.com' and password 'admin123'
-- The user is marked as an admin via raw_app_meta_data.

INSERT INTO auth.users (
    instance_id,
    id,
    aud,
    role,
    email,
    encrypted_password,
    email_confirmed_at,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at
)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '11111111-1111-1111-1111-111111111111',
    'authenticated',
    'authenticated',
    'admin@kontrolalt.com',
    extensions.crypt('admin123'::text, extensions.gen_salt('bf'::text)),
    now(),
    '{"provider":"email","providers":["email"],"is_admin":true}',
    '{}',
    now(),
    now()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO auth.identities (
    id,
    provider_id,
    user_id,
    identity_data,
    provider,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    '11111111-1111-1111-1111-111111111111',
    '11111111-1111-1111-1111-111111111111',
    format('{"sub":"%s","email":"%s"}', '11111111-1111-1111-1111-111111111111', 'admin@kontrolalt.com')::jsonb,
    'email',
    now(),
    now()
) ON CONFLICT (provider_id, provider) DO NOTHING;
