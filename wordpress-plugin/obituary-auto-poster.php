<?php
/**
 * Plugin Name: Obituary Auto Poster
 * Description: Fetches obituary posts from a FastAPI endpoint and publishes them to WordPress on a schedule.
 * Version: 1.0.0
 * Author: Obituary Content API
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

final class Obituary_Auto_Poster {
    private const OPTION_API_URL = 'oap_api_url';
    private const OPTION_LIMIT = 'oap_fetch_limit';
    private const CRON_HOOK = 'oap_fetch_obituaries_event';
    private const META_SOURCE_ID = '_oap_source_id';
    private const META_SOURCE_URL = '_oap_source_url';

    public static function init(): void {
        add_action('admin_menu', [__CLASS__, 'settings_menu']);
        add_action('admin_init', [__CLASS__, 'register_settings']);
        add_action(self::CRON_HOOK, [__CLASS__, 'fetch_and_publish']);
        add_filter('cron_schedules', [__CLASS__, 'cron_schedules']);
        add_action('wp_head', [__CLASS__, 'print_meta_description']);
    }

    public static function activate(): void {
        if (!get_option(self::OPTION_LIMIT)) {
            update_option(self::OPTION_LIMIT, 10);
        }
        if (!wp_next_scheduled(self::CRON_HOOK)) {
            wp_schedule_event(time() + 60, 'oap_fifteen_minutes', self::CRON_HOOK);
        }
    }

    public static function deactivate(): void {
        $timestamp = wp_next_scheduled(self::CRON_HOOK);
        if ($timestamp) {
            wp_unschedule_event($timestamp, self::CRON_HOOK);
        }
    }

    public static function cron_schedules(array $schedules): array {
        $schedules['oap_fifteen_minutes'] = [
            'interval' => 15 * MINUTE_IN_SECONDS,
            'display' => __('Every 15 Minutes', 'obituary-auto-poster'),
        ];
        return $schedules;
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
    }

    public static function settings_page(): void {
        if (!current_user_can('manage_options')) {
            return;
        }
        ?>
        <div class="wrap">
            <h1>Obituary Auto Poster</h1>
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
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }

    public static function fetch_and_publish(): void {
        $api_url = trim((string) get_option(self::OPTION_API_URL));
        if (!$api_url) {
            return;
        }

        $limit = min(max((int) get_option(self::OPTION_LIMIT, 10), 1), 50);
        $url = add_query_arg(['page' => 1, 'limit' => $limit], $api_url);
        $response = wp_remote_get($url, [
            'timeout' => 15,
            'headers' => ['Accept' => 'application/json'],
        ]);

        if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) {
            return;
        }

        $payload = json_decode(wp_remote_retrieve_body($response), true);
        if (!is_array($payload) || empty($payload['items']) || !is_array($payload['items'])) {
            return;
        }

        foreach ($payload['items'] as $item) {
            if (is_array($item)) {
                self::publish_item($item);
            }
        }
    }

    private static function publish_item(array $item): void {
        if (!function_exists('post_exists')) {
            require_once ABSPATH . 'wp-admin/includes/post.php';
        }
        if (!function_exists('wp_insert_category')) {
            require_once ABSPATH . 'wp-admin/includes/taxonomy.php';
        }

        $title = sanitize_text_field($item['title'] ?? '');
        $slug = sanitize_title($item['slug'] ?? $title);
        $source_id = sanitize_text_field($item['_id'] ?? $item['id'] ?? '');

        if (!$title || !$slug || self::post_exists($slug, $title, $source_id)) {
            return;
        }

        $category_id = self::obituaries_category_id();
        $content = wp_kses_post(wpautop((string) ($item['content'] ?? '')));
        $post_id = wp_insert_post([
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
        ], true);

        if (!is_wp_error($post_id) && !empty($item['date_of_death'])) {
            update_post_meta($post_id, '_oap_date_of_death', sanitize_text_field($item['date_of_death']));
        }
    }

    private static function post_exists(string $slug, string $title, string $source_id): bool {
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
                return true;
            }
        }

        $by_slug = get_page_by_path($slug, OBJECT, 'post');
        if ($by_slug) {
            return true;
        }

        return post_exists($title) !== 0;
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
}

Obituary_Auto_Poster::init();
register_activation_hook(__FILE__, ['Obituary_Auto_Poster', 'activate']);
register_deactivation_hook(__FILE__, ['Obituary_Auto_Poster', 'deactivate']);
