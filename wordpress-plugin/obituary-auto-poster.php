<?php
/**
 * Plugin Name: Obituary Auto Poster
 * Description: Fetches obituary posts from a FastAPI endpoint and publishes them when called by a secure external trigger.
 * Version: 1.1.0
 * Author: Obituary Content API
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

final class Obituary_Auto_Poster {
    private const OPTION_API_URL = 'oap_api_url';
    private const OPTION_LIMIT = 'oap_fetch_limit';
    private const OPTION_TRIGGER_TOKEN = 'oap_trigger_token';
    private const CRON_HOOK = 'oap_fetch_obituaries_event';
    private const META_SOURCE_ID = '_oap_source_id';
    private const META_SOURCE_URL = '_oap_source_url';
    private const REST_NAMESPACE = 'obituary-auto-poster/v1';
    private const REST_ROUTE = '/run';

    public static function init(): void {
        add_action('admin_menu', [__CLASS__, 'settings_menu']);
        add_action('admin_init', [__CLASS__, 'register_settings']);
        add_action('rest_api_init', [__CLASS__, 'register_rest_routes']);
        add_action('wp_head', [__CLASS__, 'print_meta_description']);
    }

    public static function activate(): void {
        if (!get_option(self::OPTION_LIMIT)) {
            update_option(self::OPTION_LIMIT, 10);
        }
        if (!get_option(self::OPTION_TRIGGER_TOKEN)) {
            update_option(self::OPTION_TRIGGER_TOKEN, self::generate_token());
        }
        self::clear_legacy_cron();
    }

    public static function deactivate(): void {
        self::clear_legacy_cron();
    }

    public static function settings_menu(): void {
        add_options_page(
            'Obituary Auto Poster',
            'Obituary Auto Poster',
            'manage_options',
            'obituary-auto-poster',
            [__CLASS__, 'settings_page']
        );
    }

    public static function register_settings(): void {
        register_setting('oap_settings', self::OPTION_API_URL, [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => '',
        ]);
        register_setting('oap_settings', self::OPTION_LIMIT, [
            'type' => 'integer',
            'sanitize_callback' => 'absint',
            'default' => 10,
        ]);
        register_setting('oap_settings', self::OPTION_TRIGGER_TOKEN, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_token'],
            'default' => '',
        ]);
    }

    public static function settings_page(): void {
        if (!current_user_can('manage_options')) {
            return;
        }
        $token = get_option(self::OPTION_TRIGGER_TOKEN);
        if (!$token) {
            $token = self::generate_token();
            update_option(self::OPTION_TRIGGER_TOKEN, $token);
        }
        $trigger_url = rest_url(self::REST_NAMESPACE . self::REST_ROUTE);
        $trigger_url_with_token = add_query_arg('token', rawurlencode($token), $trigger_url);
        ?>
        <div class="wrap">
            <h1>Obituary Auto Poster</h1>
            <p>This plugin does not use WordPress cron. Call the secure trigger URL from an external scheduler such as cron-job.org, Render cron, GitHub Actions, or cPanel cron.</p>
            <form method="post" action="options.php">
                <?php settings_fields('oap_settings'); ?>
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row"><label for="<?php echo esc_attr(self::OPTION_API_URL); ?>">API URL</label></th>
                        <td>
                            <input
                                name="<?php echo esc_attr(self::OPTION_API_URL); ?>"
                                id="<?php echo esc_attr(self::OPTION_API_URL); ?>"
                                type="url"
                                class="regular-text"
                                value="<?php echo esc_attr(get_option(self::OPTION_API_URL)); ?>"
                                placeholder="https://your-api.example.com/api/obituaries"
                            />
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="<?php echo esc_attr(self::OPTION_LIMIT); ?>">Posts per fetch</label></th>
                        <td>
                            <input
                                name="<?php echo esc_attr(self::OPTION_LIMIT); ?>"
                                id="<?php echo esc_attr(self::OPTION_LIMIT); ?>"
                                type="number"
                                min="1"
                                max="50"
                                value="<?php echo esc_attr((int) get_option(self::OPTION_LIMIT, 10)); ?>"
                            />
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="<?php echo esc_attr(self::OPTION_TRIGGER_TOKEN); ?>">Trigger token</label></th>
                        <td>
                            <input
                                name="<?php echo esc_attr(self::OPTION_TRIGGER_TOKEN); ?>"
                                id="<?php echo esc_attr(self::OPTION_TRIGGER_TOKEN); ?>"
                                type="text"
                                class="regular-text code"
                                value="<?php echo esc_attr($token); ?>"
                                autocomplete="off"
                            />
                            <p class="description">Keep this private. Change it to rotate access.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">External trigger URL</th>
                        <td>
                            <code><?php echo esc_html($trigger_url); ?></code>
                            <p class="description">Send a POST request with header <code>X-OAP-Token: your-token</code>.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Cron URL</th>
                        <td>
                            <input
                                type="text"
                                class="large-text code"
                                readonly
                                value="<?php echo esc_attr($trigger_url_with_token); ?>"
                                onclick="this.select();"
                            />
                            <p class="description">Use this full URL with cron-job.org or cPanel cron if your scheduler can only open a URL.</p>
                        </td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }

    public static function register_rest_routes(): void {
        register_rest_route(self::REST_NAMESPACE, self::REST_ROUTE, [
            'methods' => ['GET', 'POST'],
            'callback' => [__CLASS__, 'rest_run'],
            'permission_callback' => '__return_true',
        ]);
    }

    public static function rest_run(WP_REST_Request $request): WP_REST_Response {
        $configured = (string) get_option(self::OPTION_TRIGGER_TOKEN);
        $provided = (string) ($request->get_header('x-oap-token') ?: $request->get_param('token'));

        if (!$configured || !$provided || !hash_equals($configured, $provided)) {
            return new WP_REST_Response([
                'success' => false,
                'message' => 'Invalid trigger token.',
            ], 403);
        }

        $result = self::fetch_and_publish();
        return new WP_REST_Response([
            'success' => true,
            'result' => $result,
        ], 200);
    }

    public static function fetch_and_publish(): array {
        $api_url = trim((string) get_option(self::OPTION_API_URL));
        if (!$api_url) {
            return ['fetched' => 0, 'published' => 0, 'skipped' => 0, 'error' => 'API URL is not configured.'];
        }

        $limit = min(max((int) get_option(self::OPTION_LIMIT, 10), 1), 50);
        $url = add_query_arg(['page' => 1, 'limit' => $limit], $api_url);
        $response = wp_remote_get($url, [
            'timeout' => 15,
            'headers' => ['Accept' => 'application/json'],
        ]);

        if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) {
            return ['fetched' => 0, 'published' => 0, 'skipped' => 0, 'error' => 'Could not fetch API data.'];
        }

        $payload = json_decode(wp_remote_retrieve_body($response), true);
        if (!is_array($payload) || empty($payload['items']) || !is_array($payload['items'])) {
            return ['fetched' => 0, 'published' => 0, 'skipped' => 0, 'error' => 'API returned no items.'];
        }

        $published = 0;
        $updated = 0;
        $skipped = 0;
        foreach ($payload['items'] as $item) {
            if (!is_array($item)) {
                $skipped++;
                continue;
            }
            $status = self::publish_item($item);
            if ($status === 'inserted') {
                $published++;
            } elseif ($status === 'updated') {
                $updated++;
            } else {
                $skipped++;
            }
        }

        return ['fetched' => count($payload['items']), 'published' => $published, 'updated' => $updated, 'skipped' => $skipped, 'error' => null];
    }

    private static function publish_item(array $item): string {
        if (!function_exists('post_exists')) {
            require_once ABSPATH . 'wp-admin/includes/post.php';
        }
        if (!function_exists('wp_insert_category')) {
            require_once ABSPATH . 'wp-admin/includes/taxonomy.php';
        }

        $title = sanitize_text_field($item['title'] ?? '');
        $slug = sanitize_title($item['slug'] ?? $title);
        $source_id = sanitize_text_field($item['_id'] ?? $item['id'] ?? '');

        if (!$title || !$slug) {
            return '';
        }

        $existing_id = self::get_existing_post_id($slug, $title, $source_id);
        $category_id = self::obituaries_category_id();
        $content = wp_kses_post(wpautop((string) ($item['content'] ?? '')));
        
        $post_data = [
            'post_title' => $title,
            'post_name' => $slug,
            'post_content' => $content,
            'post_status' => 'publish',
            'post_type' => 'post',
            'post_category' => $category_id ? [$category_id] : [],
            'meta_input' => [
                self::META_SOURCE_ID => $source_id,
                self::META_SOURCE_URL => esc_url_raw($item['source_url'] ?? ''),
                '_yoast_wpseo_metadesc' => sanitize_text_field($item['meta_description'] ?? ''),
                '_aioseo_description' => sanitize_text_field($item['meta_description'] ?? ''),
                '_oap_meta_description' => sanitize_text_field($item['meta_description'] ?? ''),
            ],
        ];

        if ($existing_id) {
            $post_data['ID'] = $existing_id;
            $post_id = wp_update_post($post_data, true);
            $result = 'updated';
        } else {
            $post_id = wp_insert_post($post_data, true);
            $result = 'inserted';
        }

        if (is_wp_error($post_id)) {
            return '';
        }

        if (!empty($item['date_of_death'])) {
            update_post_meta($post_id, '_oap_date_of_death', sanitize_text_field($item['date_of_death']));
        }
        return $result;
    }

    private static function get_existing_post_id(string $slug, string $title, string $source_id): int {
        if ($source_id) {
            $existing = get_posts([
                'post_type' => 'post',
                'post_status' => 'any',
                'meta_key' => self::META_SOURCE_ID,
                'meta_value' => $source_id,
                'fields' => 'ids',
                'posts_per_page' => 1,
            ]);
            if ($existing) {
                return (int) $existing[0];
            }
        }

        $by_slug = get_page_by_path($slug, OBJECT, 'post');
        if ($by_slug) {
            return (int) $by_slug->ID;
        }

        return (int) post_exists($title);
    }

    private static function obituaries_category_id(): int {
        $category = get_category_by_slug('obituaries');
        if ($category) {
            return (int) $category->term_id;
        }

        $created = wp_insert_category([
            'cat_name' => 'Obituaries',
            'category_nicename' => 'obituaries',
        ]);
        return is_wp_error($created) ? 0 : (int) $created;
    }

    public static function print_meta_description(): void {
        if (!is_single()) {
            return;
        }
        $description = get_post_meta(get_the_ID(), '_oap_meta_description', true);
        if ($description) {
            printf("\n<meta name=\"description\" content=\"%s\" />\n", esc_attr($description));
        }
    }

    public static function sanitize_token(string $token): string {
        $token = preg_replace('/[^A-Za-z0-9_\-.]/', '', $token);
        return $token ?: self::generate_token();
    }

    private static function generate_token(): string {
        return wp_generate_password(40, false, false);
    }

    private static function clear_legacy_cron(): void {
        $timestamp = wp_next_scheduled(self::CRON_HOOK);
        while ($timestamp) {
            wp_unschedule_event($timestamp, self::CRON_HOOK);
            $timestamp = wp_next_scheduled(self::CRON_HOOK);
        }
    }
}

Obituary_Auto_Poster::init();
register_activation_hook(__FILE__, ['Obituary_Auto_Poster', 'activate']);
register_deactivation_hook(__FILE__, ['Obituary_Auto_Poster', 'deactivate']);
