# Feature ideas / 今後の機能案

These proposals are not implemented promises. The order reflects protection of photographs and interpretation of location estimates before convenience. / 以下は未実装の提案です。原本保護と位置推定の理解を優先しています。

| Priority | Idea / 機能案 | Benefit / 利点 | Acceptance criterion / 完了条件 |
| --- | --- | --- | --- |
| 1 | Preview and dry run / 変更前プレビュー | Show planned names, duplicates, date provenance, and GPS matches before any write. / 書き込み前に名前・重複・日付出典・GPS候補を確認。 | A test verifies no filesystem changes and that the approved plan matches execution. |
| 1 | GPS evidence report / GPS根拠レポート | Record source track, point times, time gaps, interpolation mode, and estimated accuracy. / 元ログ・点時刻・時間差・補間方法を残す。 | Every written coordinate can be traced to its input records without claiming calibrated accuracy. |
| 1 | Camera clock correction and named zones / 時計ずれ補正・地域時刻 | Specify a measured camera offset and handle historical daylight saving. / 実測した時計ずれと過去の夏時間を扱う。 | Known offset and DST-transition fixtures produce correct UTC comparisons. Ambiguous local times require a decision. |
| 2 | Track segments and speed checks / 軌跡分割・速度検査 | Avoid interpolation across disconnected GPX segments and flag implausible jumps. / 欠測区間・不自然な移動を検出。 | No interpolation crosses segment boundaries; thresholds and excluded matches are reported. |
| 2 | Small desktop interface / 小さなGUI | Choose folders, preview renaming, and inspect GPS on a local map. / フォルダー選択と命名・位置の確認を容易にする。 | Uses the same tested core; cancellation, write confirmation, and logs remain available. No map upload is implicit. |
| 2 | Complete transactional import journal / 取込履歴と復旧 | Resume interrupted runs and export original-to-output mappings. / 中断再開・元名と出力名の追跡。 | Recovery never deletes an unverified source; journal changes have regression tests. |
| 3 | XMP sidecars for sensitive RAW workflows / RAW用XMP | Add GPS without editing proprietary RAW containers. / RAW本体の編集を避ける。 | Interoperability is checked in actual photo applications and sidecars are kept with their images. |
| 3 | Signed packages and Intel Mac build / 署名・Intel Mac | Simplify installation on more machines. / 導入の手間を減らす。 | Both signing and native architecture tests pass; manuals accurately state support. |

Before adding similarity-based deduplication, define a review workflow. Two visually similar images may be distinct observations; a similarity score must never silently authorize deletion. / 類似画像検出は人による確認を前提に設計します。似た写真でも別の観察記録になり得るため、自動削除の根拠にはしません。
